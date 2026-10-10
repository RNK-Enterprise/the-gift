# The Gift on Google Play

The Android app is a **Trusted Web Activity (TWA)**: a small Android shell, built
with Google's [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap), that
opens `https://gift.rnkstudios.uk/app/` full-screen. All the app's code stays on
the website, so a release of the site is a release of the app; the store build
only changes when its icon, name or version changes.

`twa-manifest.json` here is the Bubblewrap project file. Store text and the
Play Console answers are in `store-listing.md`; graphics are in `design/play/`.

## 1. Build the app bundle (once, then for each new version)

On a machine with Node.js 18+ and a JDK 17:

```bash
npm i -g @bubblewrap/cli
cd android
bubblewrap build          # first run downloads the Android SDK and asks to create the signing key
```

Keep `android.keystore` and its passwords somewhere safe and **out of git**
(it's in `.gitignore`). Losing it means you can't update the app. Bubblewrap
writes `app-release-bundle.aab`, which is the file you upload.

For a new version, raise `appVersionCode` (and `appVersionName`) in
`twa-manifest.json`, then `bubblewrap update && bubblewrap build`.

## 2. Link the app and the site (Digital Asset Links)

Without this, Android shows a browser bar at the top of the app.

```bash
keytool -list -v -keystore android.keystore -alias thegift | grep SHA256
```

If you use **Play App Signing** (the default), also copy the SHA-256 from
Play Console → Setup → App integrity → App signing key certificate. Then, in
`deploy/the-gift.service`:

```ini
Environment=GIFT_ANDROID_PACKAGE=uk.rnkstudios.thegift
Environment=GIFT_ANDROID_CERT_SHA256=AA:BB:…(upload key),CC:DD:…(Play signing key)
```

Reinstall the unit and restart. Check:
`curl https://gift.rnkstudios.uk/.well-known/assetlinks.json`

## 3. Play Console

1. Create the app (the developer account is a one-time $25), upload the `.aab`
   to Internal testing first.
2. Fill in **Store listing** and **App content** from `store-listing.md`.
3. **Monetize → Subscriptions**: create four products with these IDs:
   `plus_monthly`, `plus_yearly`, `premium_monthly`, `premium_yearly`
   (one base plan each, auto-renewing, prices of your choice). Different IDs?
   Set `GIFT_PLAY_PRODUCTS='{"your_id":"plus",…}'`.

## 4. Let the server confirm Play purchases

The app never decides by itself that someone has paid: the server asks
Google.

1. Google Cloud Console: create a service account; enable the **Google Play
   Android Developer API**; create a JSON key.
2. Play Console → Users and permissions: invite the service account's email
   with "View financial data" and "Manage orders and subscriptions".
3. Put the key on atlas so only the service can read it, and pass it with
   systemd credentials (it never sits in the checkout):

   ```bash
   sudo install -d -m 700 /etc/the-gift
   sudo install -m 600 play-service-account.json /etc/the-gift/
   ```

   ```ini
   # deploy/the-gift.service
   LoadCredential=play.json:/etc/the-gift/play-service-account.json
   Environment=GIFT_PLAY_PACKAGE=uk.rnkstudios.thegift
   Environment=GIFT_PLAY_SERVICE_ACCOUNT=%d/play.json
   ```

The server signs Google's token request with the system `openssl`, feeding
the key through a pipe, so the key is never written anywhere else.

## 5. What the Play build hides

Inside the Play app (it opens `/app/?source=play`), the server leaves out the
translations and the one commentary whose licences don't allow use in a paid
product: the non-commercial, CrossWire-only and unknown-licence texts (23 of
139 translations, plus Robertson's Word Pictures). They stay free on the website.
