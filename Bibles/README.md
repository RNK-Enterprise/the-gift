# Bibles

139 translations across 56 languages, taken from the
[scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases)
project, which in turn converted them (mostly) from
[CrossWire SWORD](https://www.crosswire.org/sword/) modules. The translation
IDs below are the SWORD module names, so each one can be looked up in
CrossWire's module list.

## Formats

All three live under `formats/` and carry the same text.

| Folder | What it is | Needs |
|---|---|---|
| `text/` | One UTF-8 `.txt` per translation: a title line, then book / chapter headings and `N. verse` lines. The readable copy. | Nothing |
| `python/` | The same text as Python data modules (`NAME`, `BOOK`, `CHAPTERS = {chapter: {verse: text}}`), laid out twice: `python/<Translation>/<Book>.py` and `python/<Book>/<Translation>.py`. | Python 3 |
| `correlate/` | Small **Node.js** word-concordance scripts, one per book and translation, in the same two layouts. They are code, not data: each one reads its sibling file in `../../python/` at runtime, so keep the `python/` tree next to them. Words are split on letters of any script. Chinese and Japanese texts don't put spaces between words, so there a "word" is a whole run of characters between punctuation. | Node.js + `python/` |

Using a correlate script:

```bash
cd Bibles/formats/correlate
node -e "const j = require('./AKJV/John.js');
         console.log(j.occurrences('light').length);          // verses with the word
         console.log(j.correlate('light', { topN: 5 }));"      // words that co-occur with it
```

## Licensing

"Free to read" is not the same as "free to reuse". Every translation's
license is listed below. The **Licence** column takes CrossWire's current
module metadata (`DistributionLicense=` in the module's `.conf`) where it
exists, and scrollmapper's per-translation note otherwise. Where the two
disagree, the stricter one is shown and the other is noted.

| Class | Count | Meaning |
|---|---:|---|
| Public domain | 103 | Includes 2 CC0 texts. Use freely. |
| Open licence | 13 | CC BY, BY-SA, BY-ND, or GPL. Free to redistribute under that licence's terms (attribution, share-alike, no-derivatives). |
| Non-commercial | 17 | Copyrighted or CC BY-NC-*: free to read and share, **not** for commercial use; ND variants also forbid modified versions. |
| CrossWire-only permission | 3 | `LITV`, `MKJV`, `ThaiKJV`: the rights-holder granted distribution permission **to CrossWire / for use with SWORD**, not to third parties generally. |
| Unknown | 3 | `Est`, `HebModern`, `Maori`: neither source states a licence (CrossWire's Estonian note literally says "copyright status unknown"). |

If you need a strictly public-domain set, use only the rows marked
*Public domain*. The Google Play build of the app follows this rule loosely:
it hides every *Non-commercial*, *CrossWire-only* and *Unknown* row, so the
paid app ships only public-domain and open-licence texts (116 of 139); the
website keeps all of them free to read, and none of them is ever part of a
paid feature such as offline downloads. Before redistributing anything else, check its terms.
For the CrossWire-only and Unknown rows, ask the rights-holder.

| ID | Lang | Title | Licence | Class |
|---|---|---|---|---|
| `ACV` | en | A Conservative Version | Public Domain | Public domain |
| `AKJV` | en | American King James Version | Copyrighted; Free non-commercial distribution | Non-commercial |
| `Alb` | sq | Albanian Bible | Public Domain | Public domain |
| `Anderson` | en | Henry Tompkins Anderson’s 1864 New Testament | Public Domain | Public domain |
| `ArmEastern` | hy | Eastern Armenian Bible | Public Domain | Public domain |
| `ASV` | en | American Standard Version (1901) | Public Domain | Public domain |
| `BBE` | en | 1949/1964 Bible in Basic English | Public Domain | Public domain |
| `BeaMRK` | bea | The Gospel of Mark in Beaver (Danezaa) | Public Domain | Public domain |
| `BSB` | en | Berean Standard Bible | CC0 | Public domain |
| `BurJudson` | my | 1835 Judson Burmese Bible | Public Domain | Public domain |
| `Byz` | grc | The New Testament in the Original Greek: Byzantine Textform 2013 | CC BY-NC-SA 4.0 | Non-commercial |
| `CebPinadayag` | ceb | Cebuano Pinadayag | Public Domain | Public domain |
| `Che1860` | chr | Cherokee New Testament (1860) with Sequoyah transliterated forms | Public Domain | Public domain |
| `ChiSB` | zh-hant | 思高本 (Sīgāo Běn), 聖經：思高聖經學會譯釋 | Public Domain | Public domain |
| `ChiUn` | zh-hant | 和合本 (繁體字) | Public Domain | Public domain |
| `ChiUnL` | lzh | 聖經 (文理和合) | Public Domain | Public domain |
| `CopSahBible2` | cop-sa | Sahidic Bible 2 | CC BY-SA | Open licence |
| `CPDV` | en | Catholic Public Domain Version | Public Domain | Public domain |
| `CroSaric` | hr | Hrvatska Biblija Ivana Šarića | Public Domain | Public domain |
| `CSlElizabeth` | cu | 1757 Church Slavonic Elizabeth Bible | Public Domain | Public domain |
| `CzeBKR` | cs | Czech Bible Kralicka | Public Domain | Public domain |
| `CzeCSP` | cs | Czech Český studijní překlad | CC BY-NC-ND 4.0 | Non-commercial |
| `DaOT1871NT1907` | da | Danish OT1871 + NT1907 with original orthography | Public Domain | Public domain |
| `Darby` | en | Darby Bible (1889) | Public Domain | Public domain |
| `DRC` | en | Douay-Rheims Bible, Challoner Revision | Public Domain | Public domain |
| `DutSVV` | nl | Dutch Statenvertaling Bijbel | Public Domain | Public domain |
| `DutSVVA` | nl | De ganse Heilige Schrift bevattende al de kanonieke boeken van het Oude en Nieuwe Testament, met de apocriefe (deuterocanonieke) boeken | Public Domain | Public domain |
| `Esperanto` | eo | Esperanto Londona Biblio | Public Domain | Public domain |
| `Est` | et | Estonian Bible | Unknown | Unknown — no license in either source |
| `FinBiblia` | fi | Finnish Biblia (1776) | Public Domain | Public domain |
| `FinPR` | fi | Finnish Pyhä Raamattu (1933/1938) | Public Domain | Public domain |
| `FinSTLK2017` | fi | Pyhä Raamattu (STLK 2017) | CC BY-NC-ND 4.0 | Non-commercial |
| `FreBBB` | fr | French Bible Bovet Bonnet (1900) | Copyrighted; Free non-commercial distribution | Non-commercial — not in CrossWire metadata; license from scrollmapper only |
| `FreBDM1744` | fr | Bible David Martin (1744) | Public Domain | Public domain |
| `FreCrampon` | fr | La Bible Augustin Crampon 1923 | Public Domain | Public domain |
| `FreGeneve1669` | fr | Le Nouveau Testament de la Bible de Genève de 1669 | Public Domain | Public domain |
| `FreJND` | fr | Bible J.N. Darby in French with Strong's numbers | Public Domain | Public domain |
| `FreLXX` | fr | Traduction de la LXX par P. GIGUET et autres traducteurs, 1872. | Public Domain | Public domain — not in CrossWire metadata; license from scrollmapper only |
| `FreLXXGiguet` | fr | Traduction de la LXX par Pierre GIGUET et autres traducteurs, 1872. | Public Domain | Public domain |
| `FreOltramare1874` | fr | Le Nouveau Testament Version Oltramare 1874 | Public Domain | Public domain |
| `FrePGR` | fr | Bible Perret-Gentil et Rilliet | Public Domain | Public domain |
| `FreStapfer1889` | fr | Le Nouveau Testament traduction de Stapfer - 1889 | Public Domain | Public domain |
| `FreSynodale1921` | fr | Le Nouveau Testament Version Synodale 1921 et le livre des Psaumes | Public Domain | Public domain |
| `Geneva1599` | en | Geneva Bible (1599) | Public Domain | Public domain |
| `GerAlbrecht` | de | German Albrecht Neues Testament und Psalmen | Public Domain | Public domain |
| `GerBoLut` | de | Deutsch Bolsingerߴs Luther 1545 Bibel (moderne Rechtschreibung) | Public Domain | Public domain |
| `GerElb1871` | de | German Elberfelder (1871) (sogenannt) | Public Domain | Public domain |
| `GerElb1905` | de | German Darby Unrevidierte Elberfelder (1905) | Public Domain | Public domain |
| `GerGruenewald` | de | 1924 Grünewaldbibel | Public Domain | Public domain |
| `GerLeoNA28` | de | Leonberger Bibel, NT (NA28) | CC BY-NC-ND 4.0 | Non-commercial |
| `GerMenge` | de | Menge-Bibel (1939) | Public Domain | Public domain |
| `GerOffBiSt` | de | Offene Bibel - Studienfassung | CC BY-SA 4.0 | Open licence |
| `GerSch` | de | Schlachter Bibel (1951) | Copyrighted; Free non-commercial distribution | Non-commercial |
| `GerTafel` | de | German Tafelbibel (1911) | Public Domain | Public domain |
| `GerTextbibel` | de | Deutsch Textbibel (1906) | Public Domain | Public domain |
| `GerZurcher` | de | Deutsche Zürcher Bibel von 1931. | Public Domain | Public domain |
| `GreVamvas` | el | Neophytos Vamvas's translation of the Holy Bible into modern Greek (1850) | Public Domain | Public domain |
| `Haitian` | ht | Haitian Creole Bible | Public Domain | Public domain |
| `Haweis` | en | Thomas Haweis 1795 New Testament | Public Domain | Public domain |
| `HebModern` | he | Modern Hebrew Bible | Unknown | Unknown — no license in either source |
| `HunKar` | hu | Revideált Károli Biblia 1908 | Public Domain | Public domain |
| `JapBungo` | ja | 明治元訳「舊約聖書」(1953年版) 大正改訳「新約聖書 | Public Domain | Public domain |
| `JapDenmo` | ja | Japanese Denmo 電網聖書 | Public Domain | Public domain |
| `JapKougo` | ja | Japanese Kougo-yaku 口語訳「聖書」(1954/1955年版) | Public Domain | Public domain |
| `JPS` | en | Jewish Publication Society Old Testament | Public Domain | Public domain |
| `Jubilee2000` | en | English Jubilee 2000 Bible | Copyrighted; Free non-commercial distribution | Non-commercial |
| `KJV` | en | King James Version (1769) with Strongs Numbers and Morphology and CatchWords | GPL | Open licence |
| `KJVA` | en | King James Version (1769) with Strongs Numbers and Morphology and CatchWords, including Apocrypha (without glosses) | GPL | Open licence |
| `KJVPCE` | en | King James Version: Pure Cambridge Edition | Public Domain | Public domain |
| `KLV` | tlh | Klingon Language Version of the World English Bible | Public Domain | Public domain |
| `KorHKJV` | ko | Hangul King James Version | Copyrighted; Free non-commercial distribution | Non-commercial |
| `KorRV` | ko | 개역성경 | Public Domain | Public domain |
| `LEB` | en | The Lexham English Bible | Copyrighted; Free non-commercial distribution | Non-commercial |
| `LITV` | en | Green's Literal Translation | Copyrighted; Permission to distribute granted to CrossWire | CrossWire-only permission — upstream says “Copyrighted; Free non-commercial distribution” |
| `LvGluck8` | lv | Latvian Glück 8th edition | Public Domain | Public domain |
| `Mal1910` | ml | Sathyavedapusthakam (Malayalam Bible) | Public Domain | Public domain |
| `ManxGaelic` | gv | Manx Gaelic Scripture Portions | Public Domain | Public domain |
| `Maori` | mi | Maori Bible | Unknown | Unknown — no license in either source |
| `MapM` | hbo | מקרא על פי המסורה (Miqra `al pi ha-Mesorah) | CC BY-SA 4.0 | Open licence |
| `Mg1865` | mg | Baiboly Malagasy (1865) | Public Domain | Public domain |
| `MKJV` | en | Green's Modern King James Version | Copyrighted; Permission to distribute granted to CrossWire | CrossWire-only permission — upstream says “Copyrighted; Non-commercial distribution” |
| `NHEB` | en | New Heart English Bible | Public Domain | Public domain |
| `NHEBJE` | en | New Heart English Bible: Jehovah Edition | Public Domain | Public domain |
| `NHEBME` | en | New Heart English Bible: Messianic Edition | Public Domain | Public domain |
| `NlCanisius1939` | nl | Petrus Canisius Translation | Public Domain | Public domain |
| `Norsk` | nb | Bibelen på Norsk (1930) | Public Domain | Public domain |
| `NorSMB` | nn | Studentmållagsbibelen frå 1921 | Public Domain | Public domain |
| `Noyes` | en | 1869 Noyes Translation | Public Domain | Public domain |
| `OEB` | en | Open English Bible (US Spelling) | CC0 | Public domain |
| `OEBcth` | en | Open English Bible (Commonwealth Spelling) | CC0 | Public domain |
| `Peshitta` | syr | Syriac Peshitta | Public Domain | Public domain |
| `PohnOld` | pon | Old Public Domain Pohnpeian Bible | Public Domain | Public domain |
| `PolGdanska` | pl | Polish Biblia Gdanska (1881) | Public Domain | Public domain |
| `PolUGdanska` | pl | Updated Gdańsk Bible | Copyrighted; Free non-commercial distribution | Non-commercial |
| `PorBLivre` | pt | Bíblia Livre | CC BY 3.0 BR | Open licence |
| `PorBLivreTR` | pt | Bíblia Livre - Textus Receptus | CC BY 3.0 BR | Open licence |
| `PorNVA` | pt | Bíblia Nova Versão de Acesso Livre | CC BY-SA 4.0 | Open licence |
| `RLT` | en | Revised Literal Translation (2018) of the King James Version with Strongs Numbers and Morphology | GPL | Open licence |
| `RNKJV` | en | Restored Name King James Version | Public Domain | Public domain |
| `Rotherham` | en | The Emphasised Bible by J. B. Rotherham | Public Domain | Public domain |
| `RusMakarij` | ru | The Pentateuch of Moses in Russian | Public Domain | Public domain |
| `RusSynodal` | ru | Синодального Перевода Библии | Public Domain | Public domain |
| `RWebster` | en | Revised Webster Version (1833) | Public Domain | Public domain |
| `SloChraska` | sl | A Conservative Version | CC BY-NC-ND 4.0 | Non-commercial — upstream says “Public Domain” |
| `SloKJV` | sl | Slovenian translation of Holy Bible King James Version (1769) | CC BY-NC-ND 4.0 | Non-commercial |
| `SloOjacano` | sl | Ojačano Sveto pismo (Ps + Gal) | Copyrighted; Free non-commercial distribution | Non-commercial |
| `SloStritar` | sl | Novi testament in Psalmi Davidovi Josipa Stritarja (1882) | Public Domain | Public domain |
| `sml_BL_2008` | sml | Kitab Awal-Jaman maka Kitab Injil | CC BY-ND 3.0 | Open licence |
| `SP` | hbo | Samaritan Pentateuch | Copyrighted; Free non-commercial distribution | Non-commercial |
| `SpaPlatense` | es | Biblia Platense (Straubinger) | Public Domain | Public domain |
| `SpaRV` | es | La Santa Biblia Reina-Valera (1909) | Public Domain | Public domain |
| `SpaRV1865` | es | La Santa Biblia Reina-Valera (1865) con arreglos ortográficos | Public Domain | Public domain |
| `SrKDEkavski` | sr | Serbian Bible Daničić-Karadžić Ekavski | Public Domain | Public domain |
| `SrKDIjekav` | sr | Serbian Bible Daničić-Karadžić Ijekavski | Public Domain | Public domain |
| `StatResGNT` | grc | Statistical Restoration Greek New Testament | CC BY 4.0 | Open licence |
| `Swe1917` | sv | Swedish Bible (1917) | Public Domain | Public domain |
| `SweKarlXII` | sv | Svenska Karl XII:s Bibel (1703) | Public Domain | Public domain |
| `SweKarlXII1873` | sv | Svenska Karl XII:s Bibel (1873) | Public Domain | Public domain |
| `TagAngBiblia` | tl | Philippine Bible Society (1905) | Public Domain | Public domain |
| `Tausug` | tsg | Tausug Kitab Injil | CC BY-ND 3.0 | Open licence |
| `ThaiKJV` | th | Thai King James Version | Copyrighted; Permission to distribute granted to CrossWire | CrossWire-only permission — upstream says “Copyrighted; Free distribution” |
| `TpiKJPB` | tpi | King Jems Pisin Baibel | CC BY-NC-ND 4.0 | Non-commercial |
| `TR` | grc | Textus Receptus (1550/1894) | CC BY-NC-SA 4.0 | Non-commercial |
| `Twenty` | en | Twentieth Century New Testament | Public Domain | Public domain |
| `Tyndale` | en | William Tyndale Bible (1525/1530) | Public Domain | Public domain |
| `UKJV` | en | Updated King James Version | Public Domain | Public domain |
| `UkrOgienko` | uk | Українська Біблія. Переклад Івана Огієнка. | Public Domain | Public domain |
| `Viet` | vi | Kinh Thánh Tiếng Việt (1934) | Public Domain | Public domain |
| `vlsJoNT` | vls | Het Nieuwe Testament by Nicolaas De Jonge | Public Domain | Public domain |
| `Vulgate` | la | Latin Vulgate | Public Domain | Public domain |
| `VulgClementine` | la | Clementine Vulgate | Public Domain | Public domain |
| `VulgConte` | la | Vulgata Clementina, Conte editore | Public Domain | Public domain |
| `VulgHetzenauer` | la | Vulgata Clementina, Hetzenauer editore | Public Domain | Public domain |
| `VulgSistine` | la | Vulgata Sistina | Public Domain | Public domain |
| `Webster` | en | Webster Bible | Public Domain | Public domain |
| `WLC` | hbo | Westminster Leningrad Codex | Public Domain | Public domain |
| `Wulfila` | got | Bishop Wulfila Gothic Bible | Public Domain | Public domain |
| `Wycliffe` | enm | John Wycliffe Bible (c.1395) | CC BY-SA 4.0 | Open licence |
| `YLT` | en | Young's Literal Translation (1898) | Public Domain | Public domain |

## Repairs to upstream text

The copies here were repaired where the upstream conversion had damaged
them (fixed September 2026). Each fix was applied identically to
`text/<T>.txt` and both `python/` copies. Because `correlate/` reads
`python/`, it picks the fixes up automatically.

- **`Alb`, `HebModern`, `CroSaric`**: the last verse of each (Rev 22:21,
  Rev 22:21, 2 Macc 15:39) had another Bible's Unbound Bible file header
  glued onto it (`#THE UNBOUND BIBLE … #name Chinese: NCV …`, Italian
  Diodati, Ukrainian Kulish). The header was removed and the verse kept.
- **`Viet`**: 21 words where UTF-8 had been decoded as Latin-1 and lost
  bytes (`Tr»»i` → `Trời`, `lṀi` → `lời`, `\x80\x91ã` → `đã`, …).
  Each was restored from its context and the surrounding verses.
- **`Wulfila`**: letters the Latin→Gothic conversion had missed, some also
  mis-decoded. `Þ`/`Ã\x9e` became 𐌸, `û`/`Ã»` became 𐌿, and `ï`/`Ã¯` became 𐌹
  (the diaeresis is dropped, matching the rest of the file, which carries
  no diacritics). `Â·` became `·`, and the numeral `·µ·` became `·𐌼·`.
- **`FreBDM1744`**: one stray cp1252 dash byte in "Jésus-Christ"
  was fixed to `-`.
- **`ChiSB`**: two runs of unrecoverable junk bytes (`+?\x80+`) were
  removed, from Josh 13:13 and Jer 31:20.

- **`correlate/` (all 15,672 scripts)**: word splitting used `/[a-z0-9']+/`,
  which broke every non-English text (`bởi` became `b` + `i`, and Greek,
  Hebrew and Cyrillic produced no words at all). It now uses
  `/[\p{L}\p{M}\p{N}'’]+/gu`, which matches letters, combining marks and
  digits in any script. English results are unchanged.

If you re-pull from upstream, these problems come back unless they have
been fixed there too.

## Known gaps

- **`SpaRVG`** (Reina Valera Gómez) was removed in October 2026: all
  31,102 verse lines of its text file were empty, so there was nothing to
  read. The other Spanish texts (`SpaRV`, `SpaRV1865`, `SpaPlatense`) are
  complete.
- Partial translations (New Testament only, single books, portions) carry
  empty verse lines for the books they don't cover. That is the files'
  layout, not damage; the app hides empty books and chapters.

## Want more?

scrollmapper ships these translations (and the empty `SpaRVG`) in more formats (CSV, JSON,
SQLite, …), and CrossWire's module list has many more translations:
<https://www.crosswire.org/sword/modules/>.
