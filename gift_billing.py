"""
The Gift — plans and payments: Free, Plus, Premium (and Church, by arrangement).

What each plan unlocks is decided here and checked on the server for every
request (zero trust: the app never decides what someone has paid for).

  Free     reading, devotional, plans, journal on this device, groups,
           2 commentaries (Matthew Henry Concise, cross-references)
  Plus     + sync & backup across devices, offline Bibles
  Premium  + every commentary and the dictionaries, bigger groups,
           artist pro (more songs, listening stats)
  Church   Premium for a congregation, arranged by hand ("contact us");
           an admin grants it from the command line.

Payments: Stripe on the web, Google Play Billing in the Android app. Both
are verified with the provider before anything is granted:

  * Stripe webhooks are trusted only with a valid Stripe-Signature (HMAC),
    and subscription details are re-read from Stripe's API.
  * A Google Play purchase token from the app is checked with the Google
    Play Developer API (service account, signed with openssl from memory),
    acknowledged, and bound to one account only.

Nothing here needs a package: urllib for HTTP, hmac for signatures, and
the system's openssl binary for the RS256 signature Google requires.

Configuration (environment; payments are simply off until set):
  GIFT_STRIPE_SECRET_KEY, GIFT_STRIPE_WEBHOOK_SECRET,
  GIFT_STRIPE_PRICES      '{"plus_month":"price_…","plus_year":"price_…",
                            "premium_month":"price_…","premium_year":"price_…"}'
  GIFT_PLAY_PACKAGE       e.g. uk.rnkstudios.thegift
  GIFT_PLAY_SERVICE_ACCOUNT  path to the service account's JSON key
                          (on atlas via systemd LoadCredential=)
  GIFT_PLAY_PRODUCTS      '{"plus_monthly":"plus", …}' (defaults below)
  GIFT_CONTACT_EMAIL      where church enquiries are emailed (sendmail)
"""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from gift_community import Problem, _clean_text

TIERS = {"free": 0, "plus": 1, "premium": 2, "church": 2}
PLAN_INFO = {
    "free": {"name": "Free"},
    "plus": {"name": "Plus", "features": ["Sync & backup across devices", "Offline Bibles"]},
    "premium": {"name": "Premium", "features": ["Everything in Plus", "All 12 commentaries, cross-references and dictionaries",
                                                "Bigger groups (lead 20, up to 150 members)",
                                                "Artist pro: 100 songs and listening stats"]},
}
FEATURE_TIER = {"sync": "plus", "offline": "plus", "study": "premium", "groups": "premium", "artist": "premium"}
FREE_COMMENTARIES = {"mhcc", "tsk"}
LIMITS = {  # by tier rank
    0: {"lead_groups": 2, "group_size": 30, "songs": 10},
    1: {"lead_groups": 2, "group_size": 30, "songs": 10},
    2: {"lead_groups": 20, "group_size": 150, "songs": 100},
}
DEFAULT_PLAY_PRODUCTS = {"plus_monthly": "plus", "plus_yearly": "plus",
                         "premium_monthly": "premium", "premium_yearly": "premium"}
GRACE = 3 * 86400  # past-due subscriptions keep their plan this long

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider    TEXT NOT NULL CHECK (provider IN ('stripe', 'play', 'grant')),
  tier        TEXT NOT NULL,
  status      TEXT NOT NULL,
  period_end  INTEGER NOT NULL,
  external_id TEXT NOT NULL,
  product     TEXT NOT NULL DEFAULT '',
  customer    TEXT NOT NULL DEFAULT '',
  updated     INTEGER NOT NULL,
  UNIQUE (provider, external_id)
);
CREATE INDEX IF NOT EXISTS subscriptions_by_user ON subscriptions(user_id);
CREATE TABLE IF NOT EXISTS inquiries (
  id       INTEGER PRIMARY KEY,
  name     TEXT NOT NULL,
  church   TEXT NOT NULL,
  role     TEXT NOT NULL DEFAULT '',
  size     TEXT NOT NULL DEFAULT '',
  email    TEXT NOT NULL,
  phone    TEXT NOT NULL DEFAULT '',
  message  TEXT NOT NULL DEFAULT '',
  created  INTEGER NOT NULL,
  handled  INTEGER NOT NULL DEFAULT 0
);
"""


def _http(method, url, data=None, headers=None, timeout=20):
    body = data if isinstance(data, (bytes, type(None))) else urllib.parse.urlencode(data, doseq=True).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b"{}")
        except ValueError:
            detail = {}
        raise BillingError(f"{url.split('/')[2]} said {e.code}", detail) from e


class BillingError(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail or {}


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def rs256(private_key_pem, message):
    """Sign with the system's openssl; the key goes in through a pipe and is
    never written to disk."""
    r, w = os.pipe()
    try:
        os.write(w, private_key_pem.encode())
    finally:
        os.close(w)
    try:
        out = subprocess.run(["openssl", "dgst", "-sha256", "-sign", f"/dev/fd/{r}"],
                             input=message, capture_output=True, pass_fds=(r,), timeout=10, check=True)
    finally:
        os.close(r)
    return out.stdout


def stripe_signature_ok(payload, header, secret, tolerance=300, now=None):
    """Stripe-Signature: t=…,v1=… is an HMAC-SHA256 of 't.payload'."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t = int(parts["t"])
    except (ValueError, KeyError, AttributeError):
        return False
    if abs((now or time.time()) - t) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    sigs = [v for k, v in (p.split("=", 1) for p in header.split(",")) if k == "v1"]
    return any(hmac.compare_digest(expected, s) for s in sigs)


class Billing:
    def __init__(self, community, env=None, http=_http, sign=rs256):
        self.c = community
        self.env = env if env is not None else os.environ
        self.http = http
        self.sign = sign
        self._token = (None, 0)
        self._token_lock = threading.Lock()
        with community._write, community._db() as db:
            db.executescript(SCHEMA)

    # ----------------------------------------------------------- config

    def stripe_prices(self):
        try:
            return json.loads(self.env.get("GIFT_STRIPE_PRICES") or "{}")
        except ValueError:
            return {}

    def stripe_ready(self):
        return bool(self.env.get("GIFT_STRIPE_SECRET_KEY") and self.stripe_prices())

    def play_products(self):
        try:
            return json.loads(self.env.get("GIFT_PLAY_PRODUCTS") or "null") or DEFAULT_PLAY_PRODUCTS
        except ValueError:
            return DEFAULT_PLAY_PRODUCTS

    def play_ready(self):
        return bool(self.env.get("GIFT_PLAY_PACKAGE") and self.env.get("GIFT_PLAY_SERVICE_ACCOUNT"))

    # ------------------------------------------------------ entitlements

    def tier(self, user_id):
        """The best plan someone has right now: 'free', 'plus' or 'premium'."""
        if not user_id:
            return "free"
        now = int(time.time())
        with self.c._db() as db:
            rows = db.execute("SELECT tier, status, period_end FROM subscriptions WHERE user_id=?",
                              (user_id,)).fetchall()
        best = "free"
        for r in rows:
            live = (r["status"] in ("active", "trialing", "canceling") and r["period_end"] > now) or \
                   (r["status"] == "past_due" and r["period_end"] + GRACE > now)
            if live and TIERS.get(r["tier"], 0) > TIERS[best]:
                best = "premium" if r["tier"] == "church" else r["tier"]
        return best

    def rank(self, user_id):
        return TIERS[self.tier(user_id)]

    def allows(self, user_id, feature):
        return self.rank(user_id) >= TIERS[FEATURE_TIER[feature]]

    def require(self, user, feature):
        if not self.allows(user["id"] if user else None, feature):
            need = FEATURE_TIER[feature]
            raise Problem(402, f"This is part of {PLAN_INFO[need]['name']}.")

    def limits(self, user_id):
        return LIMITS[self.rank(user_id)]

    def status(self, user):
        with self.c._db() as db:
            rows = db.execute("SELECT provider, tier, status, period_end, product FROM subscriptions "
                              "WHERE user_id=? ORDER BY period_end DESC", (user["id"],)).fetchall()
        return {"tier": self.tier(user["id"]), "subscriptions": [dict(r) for r in rows],
                "stripe": self.stripe_ready(), "play": self.play_ready(),
                "plans": PLAN_INFO, "limits": self.limits(user["id"])}

    def _record(self, db, user_id, provider, tier, status, period_end, external_id, product="", customer=""):
        db.execute(
            "INSERT INTO subscriptions (user_id, provider, tier, status, period_end, external_id, product, customer, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(provider, external_id) DO UPDATE SET "
            "user_id=excluded.user_id, tier=excluded.tier, status=excluded.status, period_end=excluded.period_end, "
            "product=excluded.product, customer=excluded.customer, updated=excluded.updated",
            (user_id, provider, tier, status, int(period_end), external_id, product, customer, int(time.time())))

    def grant(self, username, tier, days):
        """Command line: comp a plan (a church agreement, a gift)."""
        if tier not in ("plus", "premium", "church"):
            raise Problem(400, "Tier is plus, premium or church.")
        with self.c._tx() as db:
            row = db.execute("SELECT id FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
            if row is None:
                raise Problem(404, f"No account called {username!r}.")
            self._record(db, row["id"], "grant", tier, "active", time.time() + days * 86400,
                         f"grant-{row['id']}-{tier}")
        self.c.audit("plan-granted", row["id"], "command line", tier=tier, days=days)

    # ------------------------------------------------------------ stripe

    def _stripe(self, method, path, data=None):
        key = self.env.get("GIFT_STRIPE_SECRET_KEY", "")
        return self.http(method, f"https://api.stripe.com/v1/{path}", data,
                         {"Authorization": f"Bearer {key}", "Stripe-Version": "2024-06-20"})

    def stripe_checkout(self, user, plan, period, origin):
        if not self.stripe_ready():
            raise Problem(503, "Card payments aren't set up yet.")
        price = self.stripe_prices().get(f"{plan}_{period}")
        if plan not in ("plus", "premium") or period not in ("month", "year") or not price:
            raise Problem(400, "Pick Plus or Premium, monthly or yearly.")
        with self.c._db() as db:
            row = db.execute("SELECT customer FROM subscriptions WHERE user_id=? AND provider='stripe' "
                             "AND customer!='' LIMIT 1", (user["id"],)).fetchone()
        data = {"mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": 1,
                "success_url": f"{origin}/app/#/premium?paid=1", "cancel_url": f"{origin}/app/#/premium",
                "client_reference_id": str(user["id"]), "metadata[user_id]": str(user["id"]),
                "subscription_data[metadata][user_id]": str(user["id"]), "allow_promotion_codes": "true"}
        if row:
            data["customer"] = row["customer"]
        try:
            session = self._stripe("POST", "checkout/sessions", data)
        except BillingError as e:
            raise Problem(502, "Couldn't start checkout. Try again shortly.") from e
        self.c.audit("checkout-started", user["id"], plan=plan, period=period)
        return {"url": session["url"]}

    def stripe_portal(self, user, origin):
        with self.c._db() as db:
            row = db.execute("SELECT customer FROM subscriptions WHERE user_id=? AND provider='stripe' "
                             "AND customer!='' LIMIT 1", (user["id"],)).fetchone()
        if row is None:
            raise Problem(404, "There's no card subscription on this account.")
        try:
            s = self._stripe("POST", "billing_portal/sessions", {"customer": row["customer"],
                                                                 "return_url": f"{origin}/app/#/premium"})
        except BillingError as e:
            raise Problem(502, "Couldn't open billing. Try again shortly.") from e
        return {"url": s["url"]}

    def stripe_webhook(self, payload, signature):
        secret = self.env.get("GIFT_STRIPE_WEBHOOK_SECRET", "")
        if not secret or not stripe_signature_ok(payload, signature or "", secret):
            raise Problem(400, "bad signature")
        event = json.loads(payload)
        kind, obj = event.get("type", ""), event.get("data", {}).get("object", {})
        if kind == "checkout.session.completed" and obj.get("subscription"):
            self._sync_stripe_subscription(obj["subscription"], fallback_user=obj.get("client_reference_id"))
        elif kind.startswith("customer.subscription."):
            self._sync_stripe_subscription(obj.get("id"))
        return {"received": True}

    def _sync_stripe_subscription(self, sub_id, fallback_user=None):
        """Re-read the subscription from Stripe (never trust the event body
        alone) and record what it says."""
        sub = self._stripe("GET", f"subscriptions/{urllib.parse.quote(sub_id)}")
        user_id = (sub.get("metadata") or {}).get("user_id") or fallback_user
        if not user_id or not str(user_id).isdigit():
            return
        price = ((sub.get("items") or {}).get("data") or [{}])[0].get("price", {}).get("id", "")
        tier = next((k.split("_")[0] for k, v in self.stripe_prices().items() if v == price), None)
        if tier is None:
            return
        status = sub.get("status", "canceled")
        if status == "active" and sub.get("cancel_at_period_end"):
            status = "canceling"
        period_end = sub.get("current_period_end") or (((sub.get("items") or {}).get("data") or [{}])[0]
                                                       .get("current_period_end", 0))
        with self.c._tx() as db:
            if not db.execute("SELECT 1 FROM users WHERE id=?", (int(user_id),)).fetchone():
                return
            self._record(db, int(user_id), "stripe", tier, status, period_end or 0, sub["id"], price,
                         sub.get("customer", ""))
        self.c.audit("subscription-updated", int(user_id), "stripe", tier=tier, status=status)

    # -------------------------------------------------------------- play

    def _google_token(self):
        with self._token_lock:
            token, expires = self._token
            if token and expires - 60 > time.time():
                return token
            with open(self.env["GIFT_PLAY_SERVICE_ACCOUNT"], encoding="utf-8") as f:
                sa = json.load(f)
            now = int(time.time())
            head = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
            claims = _b64url(json.dumps({
                "iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/androidpublisher",
                "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}).encode())
            signing_input = f"{head}.{claims}".encode()
            jwt = f"{head}.{claims}.{_b64url(self.sign(sa['private_key'], signing_input))}"
            out = self.http("POST", "https://oauth2.googleapis.com/token",
                            {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt})
            self._token = (out["access_token"], now + int(out.get("expires_in", 3600)))
            return self._token[0]

    def play_verify(self, user, product, token):
        """The app hands over a Play purchase token; Google says what it is."""
        if not self.play_ready():
            raise Problem(503, "Google Play billing isn't set up yet.")
        tier = self.play_products().get(product)
        if tier is None or not isinstance(token, str) or not 10 < len(token) < 4096:
            raise Problem(400, "That isn't one of our plans.")
        pkg = self.env["GIFT_PLAY_PACKAGE"]
        base = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{pkg}/purchases"
        auth = {"Authorization": f"Bearer {self._google_token()}"}
        try:
            sub = self.http("GET", f"{base}/subscriptionsv2/tokens/{urllib.parse.quote(token, safe='')}",
                            None, auth)
        except BillingError as e:
            raise Problem(402, "Google Play didn't confirm that purchase.") from e
        state = sub.get("subscriptionState", "")
        items = [i for i in sub.get("lineItems", []) if i.get("productId") == product]
        if not items:
            raise Problem(402, "Google Play didn't confirm that purchase.")
        expiry = _rfc3339(items[0].get("expiryTime", ""))
        status = {"SUBSCRIPTION_STATE_ACTIVE": "active", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "past_due",
                  "SUBSCRIPTION_STATE_CANCELED": "canceling"}.get(state, "expired")
        external = hashlib.sha256(token.encode()).hexdigest()
        with self.c._tx() as db:
            owner = db.execute("SELECT user_id FROM subscriptions WHERE provider='play' AND external_id=?",
                               (external,)).fetchone()
            if owner and owner["user_id"] != user["id"]:
                raise Problem(409, "That purchase belongs to another account.")
            self._record(db, user["id"], "play", tier, status, expiry, external, product, token)
        if sub.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING":
            try:
                self.http("POST", f"{base}/subscriptions/{product}/tokens/{urllib.parse.quote(token, safe='')}:acknowledge",
                          b"{}", {**auth, "Content-Type": "application/json"})
            except BillingError:
                pass  # retried on the next check; Google allows three days
        self.c.audit("subscription-updated", user["id"], "play", tier=tier, status=status)
        return self.status(user)

    def refresh_play(self, user):
        """Renewals happen on Google's side: re-check expired Play plans."""
        if not self.play_ready():
            return
        with self.c._db() as db:
            rows = db.execute("SELECT product, customer FROM subscriptions WHERE user_id=? AND provider='play' "
                              "AND period_end < ? AND customer != ''", (user["id"], int(time.time()))).fetchall()
        for r in rows:
            try:
                self.play_verify(user, r["product"], r["customer"])
            except Problem:
                continue

    # ---------------------------------------------------------- churches

    def church_inquiry(self, fields, ip):
        if not self.c.limits.allow(("inquiry", ip), 5, 3600):
            raise Problem(429, "Thanks! We've got your messages; we'll be in touch.")
        name, church = _clean_text(fields.get("name"), 80), _clean_text(fields.get("church"), 120)
        email = _clean_text(fields.get("email"), 120)
        if not name or not church or "@" not in email or " " in email:
            raise Problem(400, "Add your name, your church and an email address we can reply to.")
        row = (name, church, _clean_text(fields.get("role"), 60), _clean_text(fields.get("size"), 40), email,
               _clean_text(fields.get("phone"), 40), _clean_text(fields.get("message"), 2000, multiline=True))
        with self.c._tx() as db:
            db.execute("INSERT INTO inquiries (name, church, role, size, email, phone, message, created) "
                       "VALUES (?,?,?,?,?,?,?,?)", (*row, int(time.time())))
        self.c.audit("church-inquiry", None, ip, church=church)
        to = self.env.get("GIFT_CONTACT_EMAIL")
        if to:
            body = (f"To: {to}\nSubject: The Gift — church plan enquiry from {church}\n"
                    f"Content-Type: text/plain; charset=utf-8\n\n"
                    f"Name: {row[0]}\nChurch: {row[1]}\nRole: {row[2]}\nSize: {row[3]}\n"
                    f"Email: {row[4]}\nPhone: {row[5]}\n\n{row[6]}\n")
            try:
                subprocess.run(["/usr/sbin/sendmail", "-t"], input=body.encode(), timeout=15, check=False)
            except (OSError, subprocess.SubprocessError):
                pass  # it's in the database either way
        return {"ok": True}

    def inquiries(self, admin):
        self.c._require_admin(admin)
        with self.c._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM inquiries ORDER BY created DESC LIMIT 100")]


def _rfc3339(s):
    """'2026-11-10T08:00:00.123Z' → unix seconds (0 if unreadable)."""
    import datetime
    try:
        return int(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0
