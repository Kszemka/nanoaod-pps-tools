# Archiwum: zakończone kampanie

Skrypty kampanii, które już się odbyły (wyniki są w `results/`), zostawione do wglądu i do
opisu w pracy, oraz pobieranie danych i budowanie list, które już zrobiły swoje (`data3` na
Heliosie jest gotowe). Żadna obecna ścieżka (kampania Run 3, `slurm_benchmark.sbatch`,
`plot_results.py`) ich nie woła.

Nie uruchamia się ich z tego katalogu: wołają się nawzajem i resztę benchmarku przez
`test/<plik>` albo `$T/<plik>`. Przed ponownym użyciem trzeba je przenieść z powrotem, razem z
plikami, które wołają, np.:

```bash
git mv test/archive/opendata_helios.sh test/archive/slurm_fetch_opendata.sbatch \
    test/archive/opendata_index.py test/archive/fetch_opendata.sh \
    test/archive/slurm_real_vs_synthetic.sbatch test/
```

| plik | kampania | rola |
|---|---|---|
| `opendata_index.py` | Open Data | lista plików NanoAOD z CERN Open Data (URI, rozmiar, adler32) z API portalu |
| `fetch_opendata.sh` | Open Data, DAS | pobiera pliki z listy, sprawdza adler32, wznawia przerwane pobieranie |
| `opendata_helios.sh` | Open Data | na węźle logowania Heliosa wysyła pobieranie Open Data i po nim benchmark (`afterok`) |
| `slurm_fetch_opendata.sbatch` | Open Data | zadanie 1: indeks, skan, wybór ~1 TB, pobranie, weryfikacja, listy, `READY` |
| `slurm_real_vs_synthetic.sbatch` | Open Data | zadanie 2: łańcuch `--period 2016` na Open Data i punkty kontrolne na `ds_1`–`ds_96` |
| `slurm_realsyn_followup.sbatch` | Open Data | zadanie 3: powtórzenia Open Data, seria rozmiarów na Open Data, test pamięci |
| `make_head.py` | Open Data (zadanie 3) | początek pliku (pełne klastry), te same gałęzie i kodek: mniej koszyków na plik |
| `slurm_memtrace.sbatch` | pamięć | RSS w czasie przez całą pętlę: 96 plików, 1 plik i Open Data na 16–192 wątkach |
| `das_index.py` | DAS | z DAS: jedna wersja przetworzenia na (PD, era), tylko pełne kopie na dysku, pliki z rozmiarem i adler32; wybór do N GB |
| `slurm_fetch_das.sbatch` | DAS | Run 3 z DAS do `data3`: kontrole proxy i kwoty, indeks, pobranie przez AAA, weryfikacja, listy, `READY` |
| `slurm_slim11_build.sbatch` | slim11 | zadanie 0 kampanii „Łańcuch 11 filtrów na 1 TB” (`test/README.md`): zbiór z 10 gałęziami łańcucha |
| `plot_memory_compare.py` | pliki pełne vs slim | szczytowa pamięć względem liczby wątków dla dwóch zbiorów na jednym rysunku |
| `fetch_eos.sh` | Run 3 z EOS | Run 3 z EOS do `data3`: rsync po SSH przez lxplus, ręcznie w `tmux` (kod OTP na połączenie), 9 strumieni, rozmiary |
| `grid_env.sh` | Run 3 z EOS, DAS | ścieżki do env `pps-grid` (dla EOS: `kinit`); `--install` raz, `--check` pokazuje, skąd co jest |
| `slurm_fetch_eos.sbatch` | Run 3 z EOS | po `fetch_eos.sh`: rozmiary, inwentaryzacja, łańcuch na każdym pliku, listy (przeplecione, zagnieżdżone), `READY` |
| `inventory_files.py` | Tier0, Run 3 | CSV z opisem plików: zdarzenia, klastry, schemat, kodek, obecność PPS; sprawdza transfer (`data3/local.csv`, z którego `slurm_run3.sbatch` bierze liczby zdarzeń) |
| `make_filelists.py` | Tier0, Run 3 | z inwentaryzacji buduje listy `core.txt`, `weak_N.txt`, `impl.txt` i `sets.json` dla `DATASET=real` |
| `make_bigset.sh` | Open Data, H1–H4, pełne pliki | kopie `ds_1.root` … `ds_96.root` z `ds_x32.root`, wejście `DATASET=big` |
| `slurm_make_bigset.sbatch` | Open Data, H1–H4 | `make_bigset.sh` jako osobne zadanie Slurm |
| `make_slim.py` | T6, slim11 | kopia wejścia z samymi gałęziami testów (`--columns chain11`: 10 gałęzi łańcucha); z `PYTHONPATH=test`, `run_benchmark.sh` woła ją sam dla T6 i T2S |
| `run3_helios.sh` | Run 3 J1–J4 | osobne zadania Run 3 na `plgrid` (`slurm_run3.sbatch`); ostateczna kampania puszcza J1, J3 i J4 z `slurm_final.sbatch` |
| `merge_results.py` | Helios H1–H4 | łączy dwie kampanie w jeden katalog, przesuwając numery powtórzeń drugiej (`results/archive/chain5/helios-full/full-1tb`) |
| `plot_optimum.py` | Helios H1–H4, Open Data | optimum liczby wątków względem rozmiaru wejścia, z kilku katalogów wyników (wykres 14, `results/archive/chain5/layout/`; w pracy już go nie ma) |
| `plot_memory_layout.py` | pamięć | pamięć na wątek względem układu pliku (gałęzie, koszyki), dopasowanie modelu (wykres 16); importuje `plot_optimum.py` |

Wykresy `plot_*.py` i `merge_results.py` importują `plot_results.py` z `test/`, więc z archiwum
uruchamia się je z `PYTHONPATH=test`, np. `PYTHONPATH=test python test/archive/plot_optimum.py ...`.

`check_chain11.py` i `plot_real_vs_synthetic.py` wróciły do `test/` (kampania pełnych plików,
`test/README.md`); `plot_real_vs_synthetic.py` bierze teraz zbiory jako `--set DIR:TEST:LABEL`.

Opisy kampanii poniżej są przeniesione z `test/README.md`, więc ścieżki skryptów w komendach
(`test/<plik>`) dotyczą położenia sprzed archiwizacji. Ścieżki wyników są już te z obecnego
układu `results/` (`results/README.md`): łańcuch 5 filtrów w `results/archive/chain5/`, slim
w `results/synthetic-slim/`.

## Open Data (Run 2) na Helios

CERN Open Data ma 32 zbiory CMS NanoAOD, wszystkie `UL2016_MiniAODv2_NanoAODv9`: Run2016H
(~1.03 TB) i Run2016G (~1.05 TB), pliki po 1–2.5 GB. Dane są publiczne, więc nie są potrzebne
konto, certyfikat ani proxy.

Całość to trzy zadania Slurm wysłane jedną komendą z węzła logowania (z repozytorium na
scratchu): pobranie i kopie `ds_N` równolegle, benchmark po obu:

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
bash test/opendata_helios.sh                # pobranie + kopie, po nich benchmark
bash test/opendata_helios.sh --fetch-only   # samo pobranie (i kopie, jeśli brakuje)
bash test/opendata_helios.sh --bench-only   # dane już są (sprawdza READY)
bash test/opendata_helios.sh --fetch-jobs 16 --streams 2 --max-gb 1040 --dry-run
```

- **Kopie** (`slurm_make_bigset.sbatch`, 8 CPU, 8 GB, do 4 h) to `make_bigset.sh`, czyli
  `ds_1`–`ds_96.root` obok `ds_x32.root` w `$SCRATCH/bench/data`. Wysyłane tylko, jeśli którejś
  kopii brakuje; postęp w `make-bigset-<id>.out`.
- **Zadanie 1** (`slurm_fetch_opendata.sbatch`, 16 CPU, 16 GB, do 24 h, bez `--exclusive`) robi
  kroki 1–5 poniżej w `$SCRATCH/bench/data2` (`OUT_DIR`): do 1040 GB (`MAX_GB`), Run2016H
  przed Run2016G, `FETCH_JOBS=10` plików naraz, każdy `XRD_STREAMS` strumieniami `xrdcp`.
  Najpierw sprawdza, czy węzeł ma sieć do CERN; postęp (pliki, GB, MB/s) jest w
  `fetch-opendata-<id>.out`. Każdy krok pomija się, jeśli jego wynik już jest, więc przerwane
  zadanie wystarczy wysłać ponownie (`--fetch-only`). Na końcu zapisuje `READY` z podsumowaniem.
  Dane są obok `data/`, nie w nim: `STORAGE=memfs` kopiuje `data/` do RAM-u, a `DATASET=big`
  zapisuje tam `lists/`.
- **Zadanie 2** (`slurm_real_vs_synthetic.sbatch`, cały węzeł, 5 h) startuje tylko, gdy
  pobranie i kopie skończą się sukcesem (`--dependency=afterok`, a przy porażce znika z kolejki dzięki
  `--kill-on-invalid-dep=yes`). Na starcie sprawdza `READY`, `core.txt` i `ds_1`–`ds_96.root`,
  potem po kolei: `run_all.sh` (walidacja i T1 łańcucha 5 filtrów z `--period 2016` na całym
  Open Data, zimny odczyt, 1–192 wątki → `results-helios-opendata-1tb`) i `run_benchmark.sh` na
  zbiorze sztucznym w tym samym zadaniu (1, 48, 144, 192 wątki → `results-helios-control-1tb`).
  Kontrola pokazuje, czy Lustre zachowuje się tak jak w kampanii `full-1tb`. Bez kopii `ds_N`
  (`--no-control`) zadanie 2 mierzy tylko Open Data, a porównanie idzie wprost do `full-1tb`.

Jeśli węzły obliczeniowe nie mają sieci (zadanie 1 kończy się w kroku 0), to samo zadanie
działa jako zwykły skrypt na węźle logowania, w `tmux`:
`bash test/slurm_fetch_opendata.sbatch`, a potem `bash test/opendata_helios.sh --bench-only`.

Po zadaniu 2 skopiuj oba katalogi (`results-helios-opendata-1tb`, `results-helios-control-1tb`)
do `results/archive/chain5/`:

```bash
python test/plot_real_vs_synthetic.py --out results/archive/chain5/run2-opendata/1tb \
    --set "results/archive/chain5/helios-full/full-1tb:chain:artificial (96 x ds_x32)" \
    --set "results/archive/chain5/control-1tb:chain:artificial, re-measured" \
    --set "results/archive/chain5/run2-opendata/1tb:chain:Run 2 Open Data"
```

### Uzupełnienie: powtórzenia, rozmiary, pamięć

Zadanie 3 (`slurm_realsyn_followup.sbatch`, cały węzeł, do 4 h, ~2,5 h) działa na danych z
zadania 2, niczego nie pobiera. Fazy idą po kolei, `PHASES` wybiera podzbiór:

- **repeats**: r2 i r3 łańcucha na całym Open Data (zimny odczyt, 13 punktów 1–192),
  dopisane do `results-helios-opendata-1tb` z `RESUME=1`: biegi r1 są pomijane, krzywa dostaje
  takie same wąsy min–max jak zbiór sztuczny. `dataset.json` jest tam liczony od nowa, już z
  koszykami na plik.
- **sizes**: ta sama seria wątków, 3 powtórzenia, na `weak_4.txt` (~87 mln zdarzeń) i
  `weak_16.txt` (~350 mln) → `results-helios-opendata-weak4`, `-weak16`. To odpowiedniki
  `full-100m` i `full-355m` na `14_optimum_vs_size.png`.
- **memory**: `make_head.py` wycina z `ds_x32.root` pierwszą 1/32 zdarzeń (te same 1984 gałęzie
  i ZSTD:5, 36 klastrów zamiast 1110). Kopia zapisuje własne koszyki, ~7 na gałąź i klaster
  zamiast 2,3, więc plik ma ~520 tys. koszyków, ~1/10 z 5,04 mln w `ds_x32`, a nie 1/32. Trafia
  do `$SCRATCH/bench/memtest`; łańcuch czyta
  listę z 384 powtórzeniami tego pliku, z page cache, na 1, 8, 32, 96, 192 wątkach →
  `results-helios-memtest`. Obok `layout-ds_x32/` i `layout-slim11/` (jeśli `slim11` jest
  jeszcze na scratchu) z układem tych plików. Jeśli koszt wątku zależy od liczby koszyków, a nie
  od samych gałęzi, spadnie tu daleko poniżej ~200 MB z `full-11m`.

```bash
sbatch test/slurm_realsyn_followup.sbatch
sbatch --export=ALL,PHASES="memory" test/slurm_realsyn_followup.sbatch   # sama faza
```

Każdy katalog wyników dostaje `dataset.json` (`dataset_json.py`): liczbę plików, zdarzenia,
zakres gałęzi, a z próbki do 5 plików medianę gałęzi, klastrów i koszyków na plik oraz kodek.
Po skopiowaniu katalogów do `results/archive/chain5/`:

```bash
python test/plot_real_vs_synthetic.py --out results/archive/chain5/run2-opendata/1tb \
    --set "results/archive/chain5/helios-full/full-1tb:chain:artificial (96 x ds_x32)" \
    --set "results/archive/chain5/control-1tb:chain:artificial, re-measured" \
    --set "results/archive/chain5/run2-opendata/1tb:chain:Run 2 Open Data"
python test/plot_optimum.py --tests chain --out results/archive/chain5/layout \
    --results results/archive/chain5/helios-full/full-{11m,100m,355m,1tb} \
    results/archive/chain5/run2-opendata/{89m,356m,1tb}
python test/plot_memory_layout.py --out results/archive/chain5/layout \
    --set "results/synthetic-slim:chain11:slim:results/archive/chain5/memtest/layout-slim11" \
    --set "results/archive/chain5/helios-full/full-11m:chain:ds_x32:results/archive/chain5/memtest/layout-ds_x32" \
    --set "results/archive/chain5/helios-full/full-1tb:chain:ds_x32 x96:results/archive/chain5/memtest/layout-ds_x32" \
    --set "results/archive/chain5/memtest:chain:ds_x32 head" \
    --set "results/archive/chain5/run2-opendata/89m:chain:Open Data 89 M" \
    --set "results/archive/chain5/run2-opendata/356m:chain:Open Data 356 M" \
    --set "results/archive/chain5/run2-opendata/1tb:chain:Open Data 1 TB"
```

`plot_optimum.py` rysuje przemiatania z `--period 2016` jako osobną serię (trójkąty).
`plot_memory_layout.py` dopasowuje do nachylenia RSS względem wątków model
`MB/wątek = a + b·gałęzie + c·koszyki na plik` i wypisuje resztę dla każdego wejścia: każdy
TTree otwarty przez wątek trzyma indeks koszyków (rozmiar, pierwsze zdarzenie, pozycja w pliku)
każdej gałęzi, czytanej czy nie. Układ wejścia bierze z `dataset.json` w katalogu wyników albo z
czwartego pola `--set` (katalog z `dataset.json` albo ręcznie `GAŁĘZIE/KOSZYKI`, np. `1984/5037148`
dla `ds_x32`). Przy 7 wejściach i 3 parametrach reszty coś mówią; przy 3 dopasowanie jest
dokładne. Model dostaje nachylenie z całej serii wątków; tabela i CSV podają też nachylenie do
32 i od 32 wątków, bo na wejściach z wielu plików RSS nie rośnie liniowo (`full-1tb`: 385 i
124 MB/wątek).

### RSS w trakcie pętli (`slurm_memtrace.sbatch`)

`peak_rss_kb` to `getrusage(RUSAGE_SELF).ru_maxrss`: najwyższy RSS procesu w całym biegu,
liczony przez jądro (zgodny z `/usr/bin/time`). Przebieg w czasie (`rss_*.csv`, rysunek 06)
zbierał do niedawna wątek Pythona, a pętla C++ wywołana z PyROOT trzyma GIL, więc wcześniejsze
kampanie (`rss_trace_source` = `statm`) nie mają ani jednej próbki z pętli. Teraz próbki
zbiera osobny proces z `/proc/<pid>/statm` (`statm-process`). Zadanie (cały węzeł, ~20 min)
mierzy łańcuch na 16, 48, 128 i 192 wątkach, 2 powtórzenia, zimny odczyt, próbka co 0,05 s,
na trzech wejściach: 96 kopiach `ds_x32` (`results-helios-memtrace-96files`), samym
`ds_x32.root` (`-1file`) i Open Data (`-opendata`). Ma pokazać, skąd zagięcie krzywej szczytu
na 96 plikach: dwa drzewa na wątek przy przejściu do kolejnego pliku i mniej żywych drzew, gdy
wątki czekają na Lustre.

```bash
sbatch test/slurm_memtrace.sbatch
sbatch --export=ALL,PHASES="files96 file1" test/slurm_memtrace.sbatch   # bez Open Data
```

Ręcznie te same kroki wyglądają tak:

```bash
cd $SCRATCH/bench/data2                         # lub lxplus: tylko kroki 1-3
T=$SCRATCH/bench/nanoaod-pps-tools/test
# 1. indeks: wszystkie pliki z URI, rozmiarem i adler32, najpierw Run2016H
python $T/opendata_index.py --era Run2016H Run2016G --output index.csv --urls scan.txt
# 2. zdalna inwentaryzacja: metadane i dwie gałęzie PPS każdego pliku (kilka % objętości)
python $T/inventory_files.py --list scan.txt --output remote.csv --jobs 8
# 3. wybór: kolumny benchmarku, PPS w >= 1% zdarzeń, dowolny schemat, do 1040 GB, H przed G
python $T/make_filelists.py --inventory remote.csv --any-schema --max-gb 1040 \
    --era-order Run2016H Run2016G --transfer-list urls.txt
# 4. pobranie (w tmux): <era>/<PD>/<plik>, adler32 sprawdzany przy każdym pliku
$T/fetch_opendata.sh --urls urls.txt --index index.csv --out-dir $PWD --jobs 10
# 5. weryfikacja (liczba zdarzeń i rozmiar plik po pliku) i listy benchmarku
python $T/inventory_files.py --list local.txt --output helios.csv --compare remote.csv
python $T/make_filelists.py --inventory helios.csv --any-schema --core-gb 1100 \
    --core-events 1e10 --out-dir $PWD
```

`fetch_opendata.sh` używa `xrdcp` (`root://eospublic.cern.ch`), a bez niego `curl` przez
`https://opendata.cern.ch/eos/...` (`--transport https`). Plik trafia pod docelową nazwę dopiero
po zgodności rozmiaru i adler32. Ponowne uruchomienie tej samej komendy pobiera tylko brakujące
pliki. Nieudane są w `failed.txt`, a `local.txt` to lista do kroku 5. `--dry-run` pokazuje, ile
zostało do pobrania i ile jest miejsca (`df`; limit grantu pokazuje `hpc-fs`). `--streams N`
dzieli każdy plik na N strumieni `xrdcp`; na końcu skrypt podaje średnią przepustowość.

Różnice wobec Tier0 2023, które trzeba uwzględnić przy porównaniu wyników:

- ~1350 gałęzi zamiast ~2000, więc mniejsza pamięć na wątek;
- schemat zmienia się między runami (inne menu HLT), dlatego `--any-schema`. Kolumny benchmarku
  są w każdym pliku, a TChain czyta tylko je;
- w 2016 PPS miał tylko detektory paskowe: `PPSLocalTrack_rpType` = 3, garnki `decRPId` 2, 3,
  102, 103. Nie ma garnków 23 i 123, diamentów (`rpType` 5) ani garnka 22, więc domyślny
  łańcuch (`--period 2023`) odrzuca wszystko już na kroku `double_arm`, a `rp_fraction` w
  inwentaryzacji wynosi 0. `bench_chain.py --period 2016` ma te same 5 kroków na garnkach z 2016
  (ramiona 2|3 i 102|103, `strip`, garnek 3); na pliku z Run2016H: 700433 → 243848 → 27762 →
  27762 → 24214 → 19459 zdarzeń;
- część plików z wczesnego Run2016G nie ma PPS wcale (odpada przy `--min-pps`).

## Run 3 z DAS (`data3`)

`slurm_fetch_das.sbatch` pobiera NanoAOD z DAS (domyślnie `/Muon*/Run2023*/NANOAOD`) przez
federację xrootd CMS (AAA, `root://cms-xrd-global.cern.ch/`) do `$SCRATCH/bench/data3`, w
układzie `<era>/<PD>/<plik>` jak Open Data, i buduje z nich listy benchmarku. Te dane nie są
publiczne: potrzebny jest certyfikat grid w `~/.globus`, członkostwo w VO `cms` i proxy VOMS.
Domyślny okres `--period 2023` to układ PPS z Run 3, więc łańcuch działa na nich bez zmian.

**Raz, na węźle logowania:** `bash test/grid_env.sh --install`. Co daje CVMFS (CA, vomses,
`dasgoclient`), bierze stamtąd. Resztę instaluje: env `pps-grid` z conda-forge (`voms`, `xrootd`,
`ca-policy-lcg`), vomses VO `cms` w `~/.voms` i `dasgoclient` z GitHuba do `$SCRATCH/bench/bin`.
`pps-bench` się nie zmienia. `bash test/grid_env.sh --check` pokazuje, skąd co jest.

**Przed każdym pobraniem, na węźle logowania** (`voms-proxy-init` pyta o hasło do klucza,
którego żaden skrypt nie przechowuje):

```bash
source test/grid_env.sh
chmod 400 ~/.globus/userkey.pem; chmod 644 ~/.globus/usercert.pem
openssl x509 -in ~/.globus/usercert.pem -noout -text \
    | grep -E 'Not After|Public-Key|Signature Algorithm|Issuer|Subject:'
voms-proxy-init --voms cms --rfc --bits 2048 --valid 48:00 --out ~/.x509up_cms   # kilka TB: do 192:00
chmod 600 ~/.x509up_cms && voms-proxy-info --all --file ~/.x509up_cms
```

`openssl` ma pokazać ważny certyfikat (`Not After` w przyszłości), klucz RSA co najmniej
2048 bitów (albo EC P-256), podpis SHA-2 (`sha256WithRSAEncryption`) i wystawcę innego niż
podmiot (CA grid, nie certyfikat self-signed). Proxy leży w katalogu domowym, bo `/tmp` węzła
logowania nie jest widoczny na węzłach obliczeniowych.

**Zadanie:**

```bash
sbatch --export=ALL,LIST_ONLY=1 test/slurm_fetch_das.sbatch    # co jest w DAS, co wybrane, co na taśmie
sbatch test/slurm_fetch_das.sbatch                             # ~1 TB (MAX_GB=1040)
sbatch --export=ALL,MAX_GB=4000 test/slurm_fetch_das.sbatch    # potem więcej, ten sam katalog
sbatch --export=ALL,CAMPAIGNS=22Sep2023 test/slurm_fetch_das.sbatch   # wybrana kampania
```

- **Krok 0, kontrole:** zadanie przerywa się, zanim cokolwiek pobierze, jeśli:
  - brakuje narzędzi;
  - proxy nie istnieje, wygasa za mniej niż `PROXY_MIN_VALID` (6 h) albo nie ma atrybutu `/cms`;
  - proxy nie należy do Ciebie, ma uprawnienia inne niż `600` albo leży w repozytorium lub w `data3`;
  - nie ma połączenia z `cmsweb.cern.ch` lub z redirectorem;
  - `MAX_GB` nie mieści się w kwocie z `lfs quota`.
- **Wybór** (`das_index.py`):
  - na każdą parę (PD, era) jedna kampania przetworzenia: pierwsza z `CAMPAIGNS` albo najnowsza, której wszystkie części mają pełną kopię na dysku;
  - z każdej części najwyższa wersja `-vN`; części `_v1`–`_v4` ery C to różne zakresy runów, więc zostają wszystkie;
  - Muon0 i Muon1 zawierają różne zdarzenia, więc zostają oba;
  - datasety tylko na taśmie trafiają na listę jako `tape-only` i są pomijane (potrzebna byłaby reguła Rucio);
  - z każdego datasetu jeden plik jest otwierany zdalnie i dataset bez kolumn benchmarku odpada;
  - budżet wypełniają kolejno ery z `ERAS` (domyślnie C, D, B), w każdej PD i nazwy plików po kolei. Ta kolejność nie zależy od `MAX_GB`, więc większy budżet tylko dokłada pliki.
- **Pobranie, weryfikacja, listy:** `fetch_opendata.sh --transport xrdcp` porównuje adler32 z DBS dla każdego pliku. Potem `inventory_files.py --compare remote.csv` sprawdza liczbę zdarzeń i rozmiar plik po pliku, a `make_filelists.py` buduje `core.txt` (cały zbiór), `weak_N.txt`, `impl.txt` i `sets.json`.
- **Wznawianie:** każdy krok pomija się, gdy jego wynik już jest, więc zadanie przerwane limitem czasu wystarczy wysłać ponownie. Proxy zostaje do sukcesu; przy `READY` zadanie je usuwa (`DELETE_PROXY=1`).
- **Zmiana zapytania lub budżetu:** `selection.txt` zapamiętuje jedno i drugie. Inne `DAS_QUERY`, `CAMPAIGNS` lub `REDIRECTOR` powtarza wszystko od indeksu, inne `MAX_GB` lub `ERAS` od wyboru. Pobrane pliki zostają.

Pozostałe zmienne: `REDIRECTOR` (np. europejski `root://xrootd-cms.infn.it/`), `FETCH_JOBS` (8),
`XRD_STREAMS` (1), `MIN_PPS` (0,01), `OUT_DIR`.

**Ile pobrać.**

- **Kwota:** limit scratcha to 12 TB, a zajęte jest ~1 TB. 10 TB zostawiłoby mniej niż 1 TB na wyniki i kopie slim, więc rozsądny sufit to ~8–9 TB.
- **Czas pobierania:** przy kilkuset MB/s z AAA 1 TB to ~1–3 h; 10 TB to jedno lub dwa zadania po 24 h, z wznowieniem.
- **Czas benchmarku:** T1 na 1 wątku rośnie z rozmiarem liniowo, czyli przy 10 TB ~1,5–2 h na sam punkt 1 wątku.
- **Czyszczenie scratcha:** przed dużym pobraniem sprawdź, po ilu dniach Cyfronet usuwa nieużywane pliki ze scratcha.
- **Zalecenie:** najpierw ~1 TB, porównywalne z `full-1tb` i `opendata-1tb`, potem ewentualnie 4 i 8 TB jako seria rozmiarów.

**Zasady.**

- Proxy to poświadczenie X.509: krótka ważność, uprawnienia `600`, nigdy w repozytorium, w skryptach ani w wynikach. Hasło do klucza podajesz tylko interaktywnie.
- Weryfikacja TLS i CA (CVMFS albo `ca-policy-lcg`) nie jest nigdzie wyłączana.
- adler32 służy tylko do kontroli integralności transferu.
- Dane zostają na scratchu.

## Prawdziwe: Tier0 replay 2023 (Ares)

Pliki z `/eos/cms/store/backfill/1/data/Tier0_REPLAY_2023/<PD>/NANOAOD/<wersja>/000/<run>/`.
Kryteria wyboru (egzekwuje je `make_filelists.py`):

- jeden run i jedna wersja przetwarzania, domyślnie **run 369998, `PromptReco-v21141959`**
  (~75 plików z różnych primary datasetów); inne runy i wersje mają inne menu HLT i inne CMSSW,
  czyli inny schemat;
- jeden skrót schematu (SHA-256 posortowanych nazw gałęzi), ten z największą liczbą zdarzeń;
- wszystkie 6 kolumn benchmarku obecne i `nPPSLocalTrack > 0` w co najmniej 1% zdarzeń;
- pliki **nie są łączone**: RDataFrame czyta listę, tak jak w analizie, a klastry zostają takie,
  jakie zapisał Tier0.

Zestawy (`make_filelists.py`, wartości z `sets.json` po inwentaryzacji na Aresie):

| lista | cel | domyślny rozmiar |
|---|---|---|
| `core.txt` | T1, T6 | do 45 mln zdarzeń albo 60 GB (budżet page cache: 192 GB RAM, ~12 GB RSS przy 48 wątkach) |
| `weak_N.txt` | T2 | ~N × (zdarzenia `core` / 48); odchylenie od celu i klastry na wątek w `sets.json` |
| `impl.txt` | T4, T5 | ~11 mln zdarzeń, jak `ds_x32`, żeby Python w T5 zmieścił się w ~20 min |

Dwie różnice wobec serii syntetycznej, które trzeba opisać razem z wynikami: kodek (produkcyjny
NanoAOD to zwykle LZMA, `ds_xN` to ZSTD:5; dekompresja to większość kosztu na zdarzenie) i
rozmiar klastrów. Oba są w kolumnach `compression` i `events_per_cluster` inwentaryzacji.

## Transfer z EOS na Ares

**1. Inwentaryzacja na lxplus** (tylko odczyt; `files.txt` to lista ścieżek jak z
`find . -name '*.root'`, względem `/eos/cms/store`):

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc12-opt/setup.sh
git clone <repo-url> nanoaod-pps-tools && cd nanoaod-pps-tools
ls /eos/cms/store/backfill/1/data/Tier0_REPLAY_2023/ | head     # sprawdź prefiks
python test/inventory_files.py --list files.txt --prefix /eos/cms/store --output inventory_lxplus.csv
python test/make_filelists.py --inventory inventory_lxplus.csv --run 369998 \
    --version PromptReco-v21141959 --transfer-list transfer.txt --strip-prefix /eos/cms/store
```

Podsumowanie na końcu inwentaryzacji grupuje pliki po (run, wersja, schemat) i pokazuje
zdarzenia, GB i średni odsetek zdarzeń z PPS. `make_filelists.py` wypisuje, ile GB trzeba przesłać.

**2. Transfer: push z lxplus przez `rsync`**, w `tmux`, 4 strumienie naraz:

```bash
DEST=plgLOGIN@ares.cyfronet.pl:/net/ascratch/people/plgLOGIN/bench/real/   # sprawdź: echo $SCRATCH
xargs -P 4 -I{} rsync -aR --partial /eos/cms/store/./{} "$DEST" < transfer.txt
```

`-R` z `/./` odtwarza strukturę katalogów od `backfill/...`, `--partial` pozwala wznowić przerwany
plik (wystarczy uruchomić tę samą komendę ponownie), a `-P 4` puszcza 4 pliki naraz. Oczekiwana
przepustowość CERN → Cyfronet to rząd 50–200 MB/s łącznie, czyli ~100 GB w 10–30 min. Logowanie
na Ares kluczem ssh z hasłem przez `ssh-agent`; klucza nie kopiuj do repo ani na scratch.

Wariant zapasowy, jeśli rsync jest wolny: pull na Aresie przez xrootd (`micromamba install -c
conda-forge xrootd` w `pps-bench`) z proxy CMS VOMS zrobionym na lxplus:

```bash
# lxplus: voms-proxy-init -voms cms -valid 24:00, potem scp pliku proxy na Ares (chmod 600)
export X509_USER_PROXY=$HOME/.x509up_cms       # poza repo i poza katalogiem wyników
sed 's|^|root://eoscms.cern.ch//eos/cms/store/|' transfer.txt > urls.txt
xrdcp --parallel 4 --infiles urls.txt $SCRATCH/bench/real/
rm -f "$X509_USER_PROXY"                        # po transferze
```

Proxy to poświadczenie X.509: krótka ważność, uprawnienia 600, nigdy w repo ani w skryptach.
Ten wariant spłaszcza strukturę katalogów, co niczemu nie szkodzi, bo nazwy plików to UUID.

**3. Weryfikacja i listy na Aresie:**

```bash
cd $SCRATCH/bench/real
find $PWD -name '*.root' -not -path '*/slim/*' > ares_files.txt
python $SCRATCH/bench/nanoaod-pps-tools/test/inventory_files.py --list ares_files.txt \
    --output inventory_ares.csv --compare inventory_lxplus.csv
python $SCRATCH/bench/nanoaod-pps-tools/test/make_filelists.py --inventory inventory_ares.csv \
    --run 369998 --version PromptReco-v21141959
```

`inventory_lxplus.csv` skopiuj wcześniej na Ares (`scp`). `--compare` porównuje liczbę zdarzeń
i rozmiar każdego pliku z inwentaryzacją z lxplus i kończy się kodem 1, jeśli choć jeden się
różni. Inwentaryzacja na Aresie liczy też `pps_fraction` (czyta tylko dwie małe gałęzie), więc
`make_filelists.py` stosuje te same kryteria co na lxplus. Listy i `sets.json` trafiają do
`$SCRATCH/bench/real`, czyli tam, gdzie `slurm_benchmark.sbatch` ustawia `DATA_DIR` dla
`DATASET=real`.

**Pojemność.** `hpc-fs` na Aresie pokazuje limity; scratch ma limity liczone w TB, więc
~100–200 GB się zmieści. Scratch jest czyszczony po ~30 dniach nieużywania. Rzeczywistym
ograniczeniem jest RAM węzła na page cache, stąd limit 60 GB dla `core.txt`.

## Run 3 z EOS przez lxplus (`data3`)

Gdy certyfikat nie jest w VO `cms`, AAA jest zamknięte, ale te same pliki leżą na EOS
(`/eos/cms/store/data/...`), który widać z lxplus. Dwie drogi odpadają:
- **xrootd prosto z EOS:** `root://eoscms.cern.ch` z biletem Kerberos spoza CERN listuje
  katalogi i podaje adler32, ale otwarcie pliku kończy się `[3012] ... Bad address`;
- **SSH w zadaniu:** lxplus spoza CERN pyta przy każdym nowym połączeniu o drugi składnik (OTP).

Zostaje więc kopiowanie rsynciem po SSH przez lxplus, ręcznie, na węźle logowania w `tmux`
(`fetch_eos.sh`), do `$SCRATCH/bench/data3/data/<era>/<PD>/NANOAOD/...`. Potem zadanie
(`slurm_fetch_eos.sbatch`) sprawdza rozmiary i buduje listy, bez łączenia się z CERN.

**Lista plików** powstaje na lxplus, bez otwierania plików ROOT: `~/run3_sizes.txt` z liniami
`<ścieżka /eos/cms/store/...> <bajty>`. Bierze tylko standardowy NanoAOD (`22Sep2023`,
`PromptNanoAOD*`, `MINIv6NANOv15`, `PromptReco`), bez wariantów grup (JME, BTV, MuoPOG, MLPF),
które mają ~2,7 × więcej bajtów na zdarzenie. `fetch_eos.sh` sam kopiuje listę z lxplus do `data3`.

**Bilet Kerberos (opcjonalnie)** sprawia, że ssh pyta tylko o kod, bez hasła. Raz: `kinit`
(`$SCRATCH/bench/micromamba/bin/micromamba install -n pps-grid -c conda-forge krb5`) i
`~/.krb5/krb5.conf` dla realmu `CERN.CH`:

```bash
mkdir -p -m 700 ~/.krb5
printf '%s\n' '[libdefaults]' ' default_realm = CERN.CH' ' forwardable = true' \
    ' rdns = false' '[realms]' ' CERN.CH = {' '  kdc = cerndc.cern.ch' ' }' \
    '[domain_realm]' ' .cern.ch = CERN.CH' >~/.krb5/krb5.conf
```

**Pobranie** (`kinit` pyta o hasło CERN, ssh o kod przy każdym z 3 połączeń; żaden skrypt ich
nie przechowuje):

```bash
tmux new -s run3
cd $SCRATCH/bench/nanoaod-pps-tools && source test/grid_env.sh
export KRB5_CONFIG=~/.krb5/krb5.conf KRB5CCNAME=FILE:$HOME/.krb5/cc_cern
kinit -f -l 25h -r 7d <login-cern>@CERN.CH && chmod 600 ~/.krb5/cc_cern
bash test/fetch_eos.sh                    # Ctrl-b d odłącza, tmux attach -t run3 wraca
sbatch test/slurm_fetch_eos.sbatch        # po „done”
```

- **Pobranie:** `CONNECTIONS` (3) połączeń SSH po `JOBS_PER_CONN` (3) rsynców, czyli 9 strumieni.
  Jedno połączenie ma jedno TCP i jeden proces szyfrujący, więc więcej strumieni daje więcej
  połączeń, a nie więcej rsynców na jednym. Pobierane są tylko pliki brakujące lub o innym
  rozmiarze, do `ATTEMPTS` (3) rund. Połączenie, które padło, jest otwierane na nowo (znowu z kodem).
- **Wznawianie:** ponowne uruchomienie `fetch_eos.sh` dociąga brakujące pliki. Na końcu usuwa
  bilet (`DELETE_TICKET=1`).
- **Zadanie:** sprawdza, że każdy plik z listy jest i ma swój rozmiar, potem `inventory_files.py`
  liczy `pps_fraction` (plik bez którejś z kolumn łańcucha 11 filtrów odpada). `check_chain11.py`
  puszcza łańcuch na każdym pliku: do `chain11_check.txt` (i `READY`) idą typy kolumn i liczniki
  po każdym filtrze zsumowane na (era, wersja), z liczbą plików, z których nic nie zostaje, do
  `chain11_files.csv` liczniki każdego pliku; `DIFFERS` przy kolumnie znaczy, że TChain jej nie
  przeczyta. Potem `make_filelists.py --interleave --nested` buduje `core.txt` (cały zbiór bez
  plików, z których po łańcuchu zostaje mniej niż `MIN_PASSED` (1) zdarzeń, pliki przeplecione
  tak, że każdy początek listy ma skład całości po erze i PD), `weak_N.txt` (N/96 zbioru,
  N = 1 … 96) i `impl.txt` (~11 M) jako kolejne początki `core.txt` i `sets.json`.
- **Więcej danych:** większa lista na lxplus, `fetch_eos.sh` jeszcze raz, usunąć `local.csv`,
  `chain11_check.txt`, `chain11_files.csv`, `sets.json` i `READY`, wysłać zadanie.

## Uruchomienie na Heliosie (192 rdzenie)

Na Ares 1 TB skaluje się aż do 48 rdzeni bez maksimum, a ds_x32 ma maksimum przy 8–16 wątkach.
Helios (partycja `plgrid`: 192 CPU, ~386 GB na węzeł) sprawdza, gdzie leży optimum, kiedy rdzeni
jest więcej. T1 biegnie na czterech rozmiarach tego samego zbioru: 11 M, 100 M, 355 M i
1065 M zdarzeń. T2 biegnie na 1 TB z 1 kopią na wątek (`WEAK_UNIT=1`): 192 wątki przy
2 kopiach na wątek potrzebowałyby 384 kopii, czyli 4 TB.

Przygotowanie, raz, na loginie:
1. Sklonuj repo do `$SCRATCH/bench/nanoaod-pps-tools`.
2. Zainstaluj micromamba do `$SCRATCH/bench/micromamba`.
3. `micromamba create -f test/environment.yml` (ROOT ma być ten sam co na Ares, 6.32.10).
4. `git lfs pull`.
5. Dane: `ds_x32.root` + `ds_1..ds_96.root` w `$SCRATCH/bench/data`. `make_bigset.sh` uzupełni
   brakujące kopie.

Cztery zadania jedno po drugim (`afterany`, więc nie dzielą Lustre):

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
export MACHINE=helios DATASET=big SIZE_SERIES="9 32"
export THREADS_LIST="1 2 4 8 12 16 24 32 48 64 80 96 128 160 192"
D=$SCRATCH/bench/data; R=$SCRATCH/bench
H="--cpus-per-task=192 --mem=384000 --output=bench-helios-%j.out --error=bench-helios-%j.err"
# H1: ds_x32, 11 M zdarzeń, 3 powtórzenia, 147 biegów, ~1 h
H1=$(sbatch --parsable $H -t 03:00:00 \
     --export=ALL,TESTS=strong,REPEATS_STRONG=3,DS_CORE=$D/ds_x32.root,RESULTS=$R/results-helios-x32 \
     test/slurm_benchmark.sbatch)
# H2: 9 kopii, ~100 GB, 2 powtórzenia, 99 biegów, ~45 min
H2=$(sbatch --parsable $H -t 03:00:00 --dependency=afterany:$H1 \
     --export=ALL,TESTS=strong,REPEATS_STRONG=2,DS_CORE=$D/lists/size_9.txt,RESULTS=$R/results-helios-c9 \
     test/slurm_benchmark.sbatch)
# H3: 32 kopie, ~350 GB, 51 biegów, ~1 h
H3=$(sbatch --parsable $H -t 04:00:00 --dependency=afterany:$H2 \
     --export=ALL,TESTS=strong,DS_CORE=$D/lists/size_32.txt,RESULTS=$R/results-helios-c32 \
     test/slurm_benchmark.sbatch)
# H4: 1 TB, T1 do 192 wątków + T2 (1 kopia na wątek) do 96, 78 biegów, ~3.5 h
sbatch $H -t 08:00:00 --dependency=afterany:$H3 \
     --export=ALL,TESTS="strong weak",WEAK_UNIT=1,WEAK_SERIES="1 2 4 8 16 32 48 64 96" \
     test/slurm_benchmark.sbatch
```

Konto i partycja są te same co na Ares (`plgccbmc15-cpu`, `plgrid`), więc przychodzą z `#SBATCH`.
`--mem=384000` zastępuje `--mem=0`: `plgrid` na Heliosie ma `MaxMemPerNode=384000` (MB), mniej niż
fizyczna pamięć węzła (386084+), więc „cała pamięć” jest odrzucana przy wysyłaniu („Memory required
by task is not available”).
`SIZE_SERIES="9 32"` sprawia, że każde zadanie pisze `lists/size_9.txt` i `lists/size_32.txt`.
`MACHINE=helios` trafia do rekordów i do nazwy domyślnego katalogu (`results-helios-big` dla H4).
Każdy rekord ma też pole `node` (nazwa węzła ze Slurma), a log zawiera `lscpu` i `numactl -H`.

Powtórka wokół maksimum na 1 TB (trzy powtórzenia, gęstsza siatka 64–192):

```bash
sbatch $H -t 03:00:00 \
     --export=ALL,TESTS=strong,RESUME=1,REPEATS_STRONG=3,THREADS_LIST="64 80 88 96 104 112 128 144 160 176 192" \
     test/slurm_benchmark.sbatch
```

Jeśli na Heliosie nie ma już `results-helios-big/raw.jsonl` z pierwszego biegu, `RESUME` nie ma
czego pominąć i zadanie liczy pełną serię r1–r3 (z t0, bez t1). Taki katalog sam w sobie nie
nadaje się do wykresów: `plot_results.py` liczy wtedy przyspieszenie względem 64 wątków. Łączy się
go z pierwszym biegiem, przesuwając powtórzenia drugiego o 1 (r1–r3 → r2–r4), łącznie ze śladami
`rss_*.csv`:

```bash
python test/merge_results.py --base results/archive/chain5/helios-full/full-1tb-job1 \
    --add results/archive/chain5/helios-full/full-1tb-job2 --shift 1 \
    --out results/archive/chain5/helios-full/full-1tb
THREAD_SCALE=linear python test/plot_results.py --results results/archive/chain5/helios-full/full-1tb
```

`THREAD_SCALE=linear` daje liniową oś wątków: przy siatce do 192 wątków zakres 96–192, gdzie leży
maksimum, zajmuje połowę osi, a nie jedną czwartą jak na osi logarytmicznej.

Optimum względem rozmiaru, po skopiowaniu wyników na laptopa:

```bash
python test/plot_optimum.py --results results/archive/chain5/helios-full/full-{11m,100m,355m,1tb} \
    --out results/archive/chain5/helios-full/full-1tb --tests chain
```

`--tests` wybiera panele rysunku (w pracy tylko łańcuch); tabela na konsoli zawsze obejmuje
wszystkie trzy operacje.

Tabela wypisuje też plateau: liczby wątków, dla których mediana czasu pętli jest w granicach 5%
od najkrótszej (mniej więcej rozrzut powtórzeń na Heliosie). Na wykresie to wąs przy najszybszym
punkcie. Dopasowane $n^*$ większe niż ostatni punkt siatki jest rysowane na tym punkcie ze strzałką
i w tabeli opisane jako `>192 (fit)`.

## Łańcuch 11 filtrów na 1 TB czytanym z dysku (Helios)

ROOT czyta tylko koszyki gałęzi, których używa analiza. Na pełnych plikach 1 TB łańcuch 5 filtrów
czyta więc z dysku tylko 28–37 GB na przebieg. W tej kampanii rozmiar zbioru wynika z liczby
przeczytanych bajtów. Pliki zawierają wyłącznie 10 gałęzi łańcucha 11 filtrów
(`bench_chain.py --chain long`, test `chain11`), więc łańcuch czyta cały plik, a zbiór ma ~1 TB.

Łańcuch to najpierw `Proton_singleRP_thetaY != 0`, `nProton_singleRP > 1`,
`PPSLocalTrack_multiRPProtonIdx >= 0`, `PPSLocalTrack_singleRPProtonIdx == -1`,
`PPSLocalTrack_time != 0` i `PPSLocalTrack_timeUnc != 0`, potem 5 starych filtrów (z RP 22).
Filtr `multiRPProtonIdx` daje dziesiątą gałąź, bo RP 22 czyta `PPSLocalTrack_decRPId` drugi raz.
Na `examples/test.root`: 346 825 → 311 565 → 294 285 → 130 697 → 75 275, potem bez zmian aż do
RP 22 (59 946) i xi (54 156). Odczyt to ~33 B na zdarzenie na dysku i 212 B po rozpakowaniu.

Zadanie 0 (`slurm_slim11_build.sbatch`, teraz w `archive/`: przed ponownym użyciem
`git mv test/archive/slurm_slim11_build.sbatch test/`; ~1–2 h, bez `--exclusive`):
1. `make_slim.py --columns chain11` na `ds_x32.root` daje `ds_x32_slim11.root`.
2. `hadd -fk` 28 kopii daje `unit.root` (310,8 M zdarzeń, ~10,3 GB). Kontrola sprawdza zdarzenia,
   gałęzie, rozmiar każdej gałęzi i kodek.
3. Próba: łańcuch na zimno na `unit.root`, 1 wątek. Daje bajty na plik i czas na zdarzenie.
4. `make_bigset.sh` robi N = ceil(1 TB / bajty na plik) kopii, najmniej 96. `copies.txt` jest
   zapisywany na końcu, a `run_benchmark.sh` bierze z niego `BIG_COPIES`.

Zadanie 1: tylko RDataFrame. `strong11` biegnie na 1–192 wątkach, bez t0 i t2, z drugim
powtórzeniem dla 96–192. `weak11` to 1 plik na wątek, do 96. `RUN_TIMEOUT=86400`, bo sam t1 to
~8–12 h; domyślne 4 h by go ubiło.

```bash
cd $SCRATCH/bench/nanoaod-pps-tools && git pull
hpc-fs                                   # ~1 TB wolnego miejsca w $SCRATCH
J0=$(sbatch --parsable test/slurm_slim11_build.sbatch)

export MACHINE=helios DATASET=big TESTS="strong11 weak11" \
    DATA_DIR=$SCRATCH/bench/slim11 RESULTS=$SCRATCH/bench/results-helios-slim11 \
    THREADS_LIST="1 4 8 12 16 24 32 48 64 80 96 112 128 144 160 176 192" \
    STRONG11_R2_THREADS="96 128 144 160 192" \
    WEAK_UNIT=1 WEAK_SERIES="1 2 4 8 16 32 48 64 96" RUN_TIMEOUT=86400
sbatch --dependency=afterok:$J0 --cpus-per-task=192 --mem=384000 -t 40:00:00 \
    --output=bench-helios-%j.out --error=bench-helios-%j.err test/slurm_benchmark.sbatch
```

`afterok`: zadanie 1 rusza tylko wtedy, gdy zbiór powstał cały. Wynik próby (bajty na plik, µs na
zdarzenie, przewidywany czas t1) jest w `slim11-build-<id>.out` i w `$SCRATCH/bench/slim11/probe.json`.
Jeśli zadanie 1 skończy się przez limit czasu, wyślij je ponownie z `RESUME=1` (wtedy bez
`--dependency`).

Kontrola po kampanii: `plot_results.py` wypisuje `read in the loop [chain11]`, czyli GB przeczytane
w pętli przez każdy przebieg. Powinno to być tyle, ile ma cały zbiór, przy każdej liczbie wątków.
Każdy rekord ma też `io_rchar_loop` i `io_read_bytes_loop` z `/proc/self/io`. Na Lustre
`io_read_bytes_loop` nie jest dokładne (0,9–1,5 × odczytu), wiarygodne są `bytes_loop` i `rchar`.

```bash
THREAD_SCALE=linear python test/plot_results.py --results results/synthetic-slim
```

Dogrywka (~2 h): powtórzenia tam, gdzie pomiar był pojedynczy albo zakłócony przez chwilowe
spowolnienie Lustre (czas 2–3 ×, za dużo zajętych rdzeni). `RESUME=1` pomija wszystkie etykiety,
które już są w `raw.jsonl`. `REPEATS_WEAK=2` dokłada całą serię `r2_weak_chain11_*`, a
`STRONG11_R3_THREADS` i `WEAK11_R3_SERIES` dają trzecie powtórzenie, więc mediana nie uśrednia
już wartości odstającej (mediana z dwóch to średnia). Do zmiennych z kampanii dochodzi:

```bash
export RESUME=1 REPEATS_WEAK=2 WEAK11_R3_SERIES="96" \
    STRONG11_R2_THREADS="96 112 128 144 160 176 192" STRONG11_R3_THREADS="144 192"
sbatch --cpus-per-task=192 --mem=384000 -t 04:00:00 \
    --output=bench-helios-%j.out --error=bench-helios-%j.err test/slurm_benchmark.sbatch
```

Druga dogrywka (~40 min): przy 144 wątkach 2 z 3 biegów były spowolnione (10–18 % więcej CPU
na zdarzenie przy tym samym odczycie, czyli wątki czekały na Lustre). `STRONG11_R4_THREADS="144 176"`
daje czwarte powtórzenie, a `STRONG11_R3_THREADS="144 176 192"` trzecie przy 176.

Trzecia dogrywka (~2 h): dwa pełne przebiegi 96–192 wątków, żeby każdy punkt miał co najmniej
4 pomiary. `STRONG11_EXTRA_REPEATS="5 6"` daje etykiety `r5_` i `r6_`; drugi przebieg idzie
w odwrotnej kolejności (192 → 96), bo spowolnienia Lustre trafiają w kilka kolejnych biegów
naraz. Listy z poprzednich dogrywek mogą zostać, bo `RESUME` i tak pomija zapisane biegi:

```bash
export MACHINE=helios DATASET=big TESTS="strong11" RESUME=1 \
    DATA_DIR=$SCRATCH/bench/slim11 RESULTS=$SCRATCH/bench/results-helios-slim11 \
    THREADS_LIST="1 4 8 12 16 24 32 48 64 80 96 112 128 144 160 176 192" \
    STRONG11_R2_THREADS="96 112 128 144 160 176 192" \
    STRONG11_R3_THREADS="144 176 192" STRONG11_R4_THREADS="144 176" \
    STRONG11_EXTRA_REPEATS="5 6" STRONG11_EXTRA_THREADS="96 112 128 144 160 176 192"
sbatch --cpus-per-task=192 --mem=384000 -t 03:00:00 \
    --output=bench-helios-%j.out --error=bench-helios-%j.err test/slurm_benchmark.sbatch
```

Biegi zakłócone: `plot_results.py` pomija bieg, którego pętla trwa ponad 1,5 × medianę tej samej
konfiguracji, o ile konfiguracja ma co najmniej 3 biegi (`OUTLIER_FACTOR`). Reguła jest ustalona
z góry i ta sama dla wszystkich kampanii. Pominięte biegi zostają w `bench.csv` ze statusem
`disturbed` i są wypisywane jako `DISTURBED: ...`. Na zbiorze slim są to r1 przy 192 wątkach
(812 s) i r1 weak przy 96 (1108 s); na pełnych plikach reguła nie pomija niczego. Biegi wolniejsze
o 5–15 % zostają: to zwykły rozrzut na współdzielonym Lustre.
