# Benchmark: RDataFrame vs Python na NanoAOD

Jedna ścieżka: `slurm_benchmark.sbatch` → `run_all.sh` → `validate.py` + `run_benchmark.sh`
→ `plot_results.py`. Te same eksperymenty idą na dwóch zbiorach: syntetycznej serii
`ds_x1`–`ds_x32` (`DATASET=synthetic`, domyślnie), prawdziwych plikach NanoAOD z Tier0
(`DATASET=real`) i na ~1 TB kopii `ds_x32.root` (`DATASET=big`, sekcja „Kampania na ~1 TB”).

| plik | rola |
|---|---|
| `run_all.sh` | sprawdza środowisko i Git LFS, uruchamia walidację, potem kampanię |
| `validate.py` | zgodność wszystkich implementacji, geometria C++ vs Python, 1 vs N wątków |
| `run_benchmark.sh` | kampania T1/T2/T4/T5/T6/T2S, zbiera `raw.jsonl`, na końcu rysuje wykresy |
| `make_slim.py` | kopia wejścia T1 z samymi 6 używanymi kolumnami (plik albo lista) dla T6 |
| `make_bigset.sh` | tylko kopiuje: `ds_1.root` … `ds_96.root` obok `ds_x32.root`, czyli wejście `DATASET=big` |
| `inventory_files.py` | CSV z opisem plików: zdarzenia, klastry, schemat, kodek, obecność PPS; sprawdza transfer |
| `make_filelists.py` | z inwentaryzacji buduje listy `core.txt`, `weak_N.txt`, `impl.txt` dla `DATASET=real` |
| `opendata_index.py` | lista plików NanoAOD z CERN Open Data (URI, rozmiar, adler32) z API portalu |
| `fetch_opendata.sh` | pobiera pliki Open Data z listy, sprawdza adler32, wznawia przerwane pobieranie |
| `opendata_helios.sh` | na węźle logowania Heliosa wysyła pobieranie Open Data i po nim benchmark (`afterok`) |
| `slurm_fetch_opendata.sbatch` | zadanie 1: indeks, skan, wybór ~1 TB, pobranie, weryfikacja, listy, `READY` |
| `slurm_make_bigset.sbatch` | `make_bigset.sh` jako osobne zadanie, równolegle z pobieraniem |
| `slurm_real_vs_synthetic.sbatch` | zadanie 2: łańcuch `--period 2016` na Open Data i punkty kontrolne na `ds_1`–`ds_96` |
| `plot_real_vs_synthetic.py` | porównanie: zbiór sztuczny, kontrola i Open Data na jednym rysunku i w tabeli |
| `slurm_realsyn_followup.sbatch` | zadanie 3: powtórzenia Open Data, seria rozmiarów na Open Data, test pamięci |
| `make_head.py` | początek pliku (pełne klastry), te same gałęzie i kodek: mniej koszyków na plik |
| `dataset_json.py` | `dataset.json` w katalogu wyników: pliki, zdarzenia, gałęzie, klastry i koszyki na plik, kodek |
| `plot_memory_layout.py` | pamięć na wątek względem układu pliku (gałęzie, koszyki), dopasowanie modelu |
| `bench_filter.py`, `bench_chain.py`, `bench_efficiency.py` | pojedynczy pomiar (TEST 1–3) |
| `bench_common.py` | parser argumentów, fazy czasu, liczniki bajtów i RSS, rekord `BENCH` |
| `impl_rdf.py`, `impl_python.py`, `impl_uproot.py` | implementacje mierzonych operacji |
| `plot_results.py` | `raw.jsonl` → `bench.csv` + wykresy (nie wymaga ROOT-a, tylko matplotlib) |
| `plot_optimum.py` | optimum liczby wątków względem rozmiaru wejścia, z kilku katalogów wyników |
| `merge_results.py` | łączy dwie kampanie w jeden katalog, przesuwając numery powtórzeń drugiej |
| `slurm_benchmark.sbatch` | zadanie na Aresie (cały węzeł, `--exclusive`) |
| `environment.yml` | środowisko `pps-bench` (ROOT, correctionlib, uproot, awkward, matplotlib) |

## Dane

Każde wejście benchmarku (`--input`) to plik `.root` albo lista `.txt` (jedna ścieżka na linię;
ścieżki względne liczone od katalogu listy). `run_benchmark.sh` przed startem sprawdza, że
istnieje każde wejście i każdy plik z każdej listy.

| rola | `DATASET=synthetic` | `DATASET=real` | `DATASET=big` |
|---|---|---|---|
| T1 (`DS_CORE`) | `ds_x32.root` | `core.txt` | `lists/core.txt` (96 kopii, ~1 TB) |
| T2 (`WEAK_PATTERN`) | `ds_x%s.root`, N = 1…32 | `weak_%s.txt`, N = 1…48 | `lists/weak_%s.txt`, 2N kopii |
| T4, T5 (`DS_IMPL`) | `ds_x32.root` | `impl.txt` (~11 mln zdarzeń) | `lists/impl.txt` (9 kopii, ~98 GB); T5 nie biegnie |
| `size`, `sizepy` (`SIZE_PATTERN`) | — | — | `lists/size_%s.txt`, N = 1, 2, 4, 6, 8, 9 kopii |

Przy `DATASET=big` listy w `$DATA_DIR/lists/` pisze sam `run_benchmark.sh` na starcie kampanii,
z pierwszych N plików `ds_1.root`, `ds_2.root`, … (wpisy `../ds_N.root`).
| T6 (`DS_SLIM`) | `ds_x32_slim.root` | `core_slim.txt` + `slim/` | domyślnie nie jest mierzony |

### Syntetyczne: `ds_xN`

Seria `ds_xN` (N kopii `examples/test.root`, ZSTD:5, autoflush 10 000) musi już leżeć
w `$DATA_DIR`.

| plik | zdarzeń | klastrów | GB | rola |
|---|---:|---:|---:|---|
| `ds_x1` | 346 825 | 36 | 0.34 | T2 przy 1 wątku |
| `ds_x2` | 693 650 | 71 | 0.68 | T2 przy 2 wątkach |
| `ds_x4` | 1 387 300 | 140 | 1.35 | T2 przy 4 wątkach |
| `ds_x8` | 2 774 600 | 279 | 2.71 | T2 przy 8 wątkach |
| `ds_x16` | 5 549 200 | 556 | 5.41 | T2 przy 16 wątkach |
| `ds_x32` | 11 098 400 | 1111 | 10.84 | T2 przy 32 wątkach **oraz całe T1, T4 i T5** |
| `ds_x32_slim` | 11 098 400 | ~1110 | — | T6; tworzony automatycznie przy pierwszym uruchomieniu |

Klastrów na wątek jest w serii praktycznie stała liczba (36.0 … 34.7), a RDataFrame dzieli pracę
po klastrach, więc para (N wątków, `ds_xN`) daje uczciwe skalowanie słabe.

`ds_x32_slim` to `Snapshot` z `ds_x32` tylko z gałęziami, które czytają testy (`nPPSLocalTrack`,
`PPSLocalTrack_{decRPId,rpType,x,y}`, `Proton_singleRP_xi`; plus gałęzie rozmiaru, które
Snapshot dopisuje dla kolumn tablicowych) zamiast 1984. `make_slim.py` przenosi kodek pliku
źródłowego i jego średni rozmiar klastra, a zapis jest jednowątkowy, więc liczba klastrów się
zgadza. Sprawdza też, że liczba zdarzeń jest identyczna. Dla listy odchudza każdy plik osobno
do `slim/` obok listy wyjściowej, a samą listę zapisuje na końcu: jeśli istnieje, jest kompletna.

### Prawdziwe: Tier0 replay 2023

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
do `results/real-1/`:

```bash
python test/plot_real_vs_synthetic.py --synthetic results/helios/full-1tb \
    --control results/real-1/results-helios-control-1tb \
    --real results/real-1/results-helios-opendata-1tb \
    --out results/real-1/results-helios-opendata-1tb
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
- **memory**: `make_head.py` wycina z `ds_x32.root` pierwszą 1/32 (te same 1984 gałęzie i
  ZSTD:5, 1/32 klastrów, więc ~1/32 koszyków na plik) do `$SCRATCH/bench/memtest`; łańcuch czyta
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
Po skopiowaniu katalogów do `results/real-1/`:

```bash
python test/plot_real_vs_synthetic.py --synthetic results/helios/full-1tb \
    --control results/real-1/results-helios-control-1tb \
    --real results/real-1/results-helios-opendata-1tb --out results/real-1/results-helios-opendata-1tb
python test/plot_optimum.py --tests chain --out results/real-1 \
    --results results/helios/full-{11m,100m,355m,1tb} \
    results/real-1/results-helios-opendata-{weak4,weak16,1tb}
python test/plot_memory_layout.py --out results/real-1 \
    --set "results/helios/slim-1.5tb:chain11:slim:results/real-1/results-helios-memtest/layout-slim11" \
    --set "results/helios/full-11m:chain:ds_x32:results/real-1/results-helios-memtest/layout-ds_x32" \
    --set "results/real-1/results-helios-memtest:chain:ds_x32 head" \
    --set "results/real-1/results-helios-opendata-1tb:chain:Open Data"
```

`plot_optimum.py` rysuje przemiatania z `--period 2016` jako osobną serię (trójkąty).
`plot_memory_layout.py` dopasowuje do nachylenia RSS względem wątków model
`MB/wątek = a + b·gałęzie + c·koszyki na plik` i wypisuje resztę dla każdego wejścia: każdy
TTree otwarty przez wątek trzyma indeks koszyków (rozmiar, pierwsze zdarzenie, pozycja w pliku)
każdej gałęzi, czytanej czy nie. Układ wejścia bierze z `dataset.json` w katalogu wyników albo z
czwartego pola `--set` (katalog z `dataset.json` albo ręcznie `GAŁĘZIE/KOSZYKI`, np. dla
`dataset.json` sprzed liczenia koszyków: Open Data `1347/263884`, mediana z pliku DoubleMuon).

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

## Kampania

| | co zmienia | wejście | wątki | powtórki | biegów |
|---|---|---|---|---|---:|
| **T1** skalowanie silne | liczbę wątków przy stałym problemie | `DS_CORE` | off, 1–48 | 5 | 150 |
| **T2** skalowanie słabe | problem i wątki naraz | `WEAK_PATTERN` | N | 3 | 54 (real: 63) |
| **T4** struktura zapytania | lazy / eager / `Report()` × długość łańcucha 1, 3, 5 | `DS_IMPL` | off | 2 | 18 |
| **T5** implementacje | RDF / correctionlib / Python / uproot, jeden rdzeń | `DS_IMPL` | off | 3 (`chain/python`: 1) | 34 + 3 |
| **T6** szerokość pliku | T1 na kopii z 6 kolumnami zamiast ~2000 gałęzi | `DS_SLIM` | off, 1–48 | 3 | 90 |
| **T2S** słabe na slim | T2 na kopiach slim | `WEAK_SLIM_PATTERN` | N | 3 | 54 (real: 63) |

`plot_results.py` dodatkowo sprawdza, że w T5 wszystkie implementacje dały tę samą liczbę
(zdarzeń po filtrze, trafień efektywności), czyli powtarza kontrolę `validate.py` na danych,
na których naprawdę mierzono.

„off” to `--threads 0`, czyli bez `EnableImplicitMT`. Punkt `t0` w T1 i T6 to drugi punkt
odniesienia dla przyspieszenia: `ImplicitMT(1)` idzie ścieżką zadaniową i jest wolniejsze od
wersji bez MT (na Aresie filtr: 4.14 s vs 3.17 s).

T4 i T5 są jednowątkowe celowo. uproot uruchamia własne wątki mimo `TrivialExecutor` w obu
executorach (na Aresie 442–444% CPU, `cores_busy_loop` 5.4–6.1), więc T5 jest przypinany do
jednego rdzenia z zewnątrz: `taskset -c $PIN_CORE` dla każdej implementacji. Rekord ma wtedy
`pinned_core`, a `cpus_allowed` i `os_threads` (wątki procesu na końcu biegu) pokazują, czy
proces rzeczywiście był ograniczony. Trzy biegi `r1_impl_*_uproot-default` (`--tag own-threads`)
to uproot bez przypięcia, tak jak dostaje go użytkownik; na wykresie 08 są osobnymi słupkami.

Biegi RDF w T5 mają tę samą konfigurację co `t0` w T1, a przy jednym powtórzeniu wychodziły
o 12–24% wolniej (łańcuch 11.07 s wobec 9.83 s, efektywność 7.69 s wobec 6.22 s, przy
`cores_busy_loop` 0.82–0.89 zamiast 1.00, jak w odrzucanych biegach `warmup_*`). Dlatego T5
ma 3 powtórzenia (poza `chain/python`, ~16 min), a `plot_results.py` wypisuje, o ile mediana
T5 odbiega od mediany T1 t0. Do porównania z innymi implementacjami w pracy lepsza jest ta
druga (5 powtórzeń).

T6 potwierdził hipotezę, że sufit skalowania na `ds_x32` bierze się z szerokości pliku. Każdy
dodatkowy wątek roboczy na pełnym pliku kosztuje (wydruk „per extra thread”):

| | RSS | odczyt w pętli | CPU w pętli |
|---|---:|---:|---:|
| pełny schemat (1984 gałęzie) | +243–245 MB | +17.98 MB | +0.94–1.03 s |
| slim (6 kolumn) | +1–3 MB | +0.05 MB | +0.04–0.11 s |

17.98 MB to dokładnie `bytes_jit`, czyli nagłówek TTree. Każdy wątek czyta i rozwija własną
kopię drzewa ze wszystkimi gałęziami, a przy wielu wątkach te budowy się serializują
(`cores_busy_loop` nasyca się na 12–14). Przyspieszenie względem wersji bez MT przy 48 wątkach:
0.79× / 2.26× / 1.37× (filtr / łańcuch / efektywność) na pełnym pliku wobec 14.8× / 18.5× /
10.9× na slim, a RSS 12.4 GB wobec 0.5–0.7 GB. Również różnica `ImplicitMT(1)` wobec wersji
bez MT to jedna taka kopia: 4.14 s wobec 3.17 s na pełnym pliku, 3.21 s wobec 3.17 s na slim.

Z tego wynikają dwa zastrzeżenia do interpretacji:

- Optimum liczby wątków w T1 nie jest cechą RDataFrame, tylko pary „rozmiar problemu × szerokość
  schematu”: stały ~1 CPU-s na wątek wobec 3–10 CPU-s całej pracy. Przy większym wejściu
  optimum przesunie się w prawo. Dopasowane $s$ z Amdahla (0.26) nie jest kodem szeregowym;
  zmierzony udział setup+JIT to 0.17.
- W T2 jednostka pracy (`ds_x1`, 0.24–0.52 s pętli na wątek) jest mniejsza niż koszt budowy
  drzewa w wątku, więc dopasowane 75–81 ms/wątek to głównie ten narzut. T2S powtarza T2 na
  kopiach slim i oddziela skalowanie samej pracy od szerokości pliku. Brakujące kopie
  (`ds_xN_slim.root`, dla list `weak_N_slim.txt`) tworzy `make_slim.py` przed rozgrzaniem cache.

T3 (pamięć) nie ma własnych biegów: każdy bieg zapisuje `peak_rss_kb` i ślad
`rss_<label>.csv` próbkowany co 0.1 s.

Przed T1 wszystkie pliki są czytane w całości (`cat > /dev/null`), żeby pierwszy bieg na
każdym pliku nie płacił za zimny odczyt z Lustre. Potem idą trzy odrzucane biegi `warmup_*`,
które płacą za zimne biblioteki ROOT-a; wykresy ich nie używają.

Razem **406 biegów, ~1.5 h** na serii syntetycznej (poprzednia kampania bez T2S i powtórzeń
T5: 327 biegów, 1.12 h) i **424 biegi, ~3–4 h** na prawdziwych danych (T1, T2 i T6 na ~4×
większym wejściu). Najdroższy jest `chain/python` z T5 (~990 s, ~16.6 GB RSS na 11 mln zdarzeń).
Każdy bieg ma limit `RUN_TIMEOUT` (2400 s); bieg, który go przekroczy albo się wywali, trafia do
`raw.jsonl` jako `"status": "failed"`.

Czas mierzony jest w fazach `setup`, `warmup`, `jit` i `loop`; porównywalna między
implementacjami jest tylko `loop`. Dla każdej fazy zapisywany jest też czas CPU procesu
(`cpu_<faza>`, suma po wątkach), a `cores_busy_loop = cpu_loop / wall_loop` mówi, ile rdzeni
średnio pracowało w pętli. `cpu_percent` z GNU time uśrednia po całym procesie, razem z ~5 s
jednowątkowego setupu, więc zaniża wykorzystanie wątków.

## Uruchomienie na Aresie

Jednorazowo, w `$SCRATCH/bench`:

```bash
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
mkdir -p micromamba && mv bin micromamba/
export MAMBA_ROOT_PREFIX=$SCRATCH/bench/micromamba
eval "$(./micromamba/bin/micromamba shell hook -s bash)"

git clone <repo-url> nanoaod-pps-tools
micromamba env create -f nanoaod-pps-tools/test/environment.yml
micromamba activate pps-bench
cd nanoaod-pps-tools && git lfs install && git lfs pull   # examples/test.root ma mieć ~240 MB
```

Seria syntetyczna w `$SCRATCH/bench/data`, listy prawdziwych danych w `$SCRATCH/bench/real`
(sekcja „Transfer z EOS na Ares”). Potem:

```bash
DRY_RUN=1 DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1                 # 406
DRY_RUN=1 DATASET=real DATA_DIR=$SCRATCH/bench/real ./test/run_benchmark.sh | tail -1    # 424
DRY_RUN=1 DATASET=big  DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1    # 99
DRY_RUN=1 DATASET=big TESTS=sizepy DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1   # 21
sbatch test/slurm_benchmark.sbatch                              # -> results-ares
sbatch --export=ALL,DATASET=real test/slurm_benchmark.sbatch    # -> results-ares-real
```

Kopie slim (`ds_x32_slim.root` i `ds_xN_slim.root` albo `core_slim.txt`, `weak_N_slim.txt` +
`slim/`) powstają przy pierwszym zadaniu, jeśli ich nie ma.

`slurm_benchmark.sbatch` bierze cały węzeł (`--exclusive`, `--mem=0`, `--hint=nomultithread`),
wypisuje `lscpu`/`nproc` i przerywa, jeśli widzi mniej CPU niż zamówił. Nie używa `srun`: od
Slurm 22.05 krok zadania nie dziedziczy `--cpus-per-task`, co po cichu spłaszcza krzywą
przyspieszenia. Istniejący katalog wyników jest przenoszony do `results-ares-archived-<data>`,
chyba że zadanie ma `RESUME=1`: wtedy dopisuje do niego i pomija etykiety, które w `raw.jsonl`
mają już `"status": "ok"`. Tak wznawia się zadanie, któremu skończył się `--time`. Biegi `failed`
są powtarzane, a `warmup_*` idą zawsze.

### Wejścia w RAM-ie (MEMFS)

```bash
sbatch -C memfs --export=ALL,STORAGE=memfs test/slurm_benchmark.sbatch                  # -> results-ares-memfs
sbatch -C memfs --export=ALL,DATASET=real,STORAGE=memfs test/slurm_benchmark.sbatch     # -> results-ares-real-memfs
```

`-C memfs` tworzy dla zadania dysk w RAM-ie pod `$MEMFS` (maks. 120 GB, wlicza się do `--mem`).
Z `STORAGE=memfs` skrypt kopiuje cały `DATA_DIR` do `$MEMFS/data` przed kampanią i dopiero
potem uruchamia te same biegi, więc żaden bieg nie czyta z Lustre. Różnica względem zwykłej
kampanii to koszt współdzielonego systemu plików. Skrypt przerywa, jeśli `$MEMFS` nie istnieje,
dane się nie mieszczą albo lista `.txt` ma ścieżkę bezwzględną (wskazywałaby dalej na Lustre).
Wyniki idą na scratch, nie do MEMFS. Każdy rekord ma pole `storage` (`lustre`/`memfs`).
Kopie slim muszą już istnieć, czyli najpierw puść zwykłą kampanię; inaczej `make_slim.py`
zapisze je w MEMFS i znikną razem z zadaniem.

### Kampania na ~1 TB (`DATASET=big`)

Najpierw jednorazowo kopie, na węźle logowania w `tmux`/`screen` (kilkanaście minut do godziny):

```bash
hpc-fs                                                            # potrzeba ~1.04 TB
bash test/make_bigset.sh --source $SCRATCH/bench/data/ds_x32.root # -> data/ds_1.root ... ds_96.root
```

Potem dwa zadania, oba do `results-ares-big`:

```bash
# A: ~3.5 h, 99 biegów -- T1 i T2 do 1 TB, T4 na ~100 GB, seria rozmiarów dla RDF i uproot
sbatch --time=06:00:00 --export=ALL,DATASET=big test/slurm_benchmark.sbatch
# B: ~9 h, 21 biegów -- ta sama seria dla Pythona, dopisana do wyników A
sbatch --time=12:00:00 --dependency=afterany:<id zadania A> \
    --export=ALL,DATASET=big,TESTS=sizepy,RESUME=1 test/slurm_benchmark.sbatch
```

`afterany` uruchamia B, gdy A się skończy, niezależnie od tego, jak się skończyło. Nie puszczaj
obu naraz: dopisywałyby do tego samego `raw.jsonl` i dzieliły Lustre, a to psuje zimne odczyty.

Wejście to 96 zwykłych kopii `ds_x32.root` (96 × 10.84 GB, ~1.04 TB, 1.065 mld zdarzeń), czyli
`ds_1.root` … `ds_96.root` w tym samym `data/`. `make_bigset.sh` tylko kopiuje: 8 strumieni `cp`,
przez nazwy `.partial`, z pominięciem kopii, które już są w dobrym rozmiarze, więc przerwane
kopiowanie wystarczy powtórzyć. Na końcu sprawdza, że wszystkie 96 ma pełny rozmiar. `df`
sprawdza wolne miejsce, ale limit grantu pokazuje tylko `hpc-fs`. Listy nad kopiami
(`lists/core.txt` = 96, `lists/weak_N.txt` = 2N, `lists/impl.txt` = 9, `lists/size_N.txt` = N
pierwszych kopii) pisze sam `run_benchmark.sh` na starcie każdego zadania. Jeśli kopii brakuje,
zadanie kończy się od razu z poleceniem, które je zrobi.

Nie `hadd`: scalanie 1 TB w jeden plik to godziny, a wynikowy plik ma inne granice klastrów niż
źródło, czyli zmienia to, po czym `ImplicitMT` dzieli pracę. `cp` zachowuje i klastry, i kodek.

**Dlaczego kopie, a nie jeden plik wpisany 96 razy na listę.** Kopia to osobny inode. Jeden plik
byłby przeczytany raz z Lustre i 95 razy z page cache, czyli kampania mierzyłaby cache. Przy
kopiach `COLD=1` (domyślne dla `big`) przed każdym biegiem wyrzuca strony wejścia z cache przez
`posix_fadvise(POSIX_FADV_DONTNEED)` — bez roota i tylko na plikach wejściowych, więc biblioteki
ROOT-a zostają ciepłe. Każdy bieg czyta wszystko z Lustre, dokładnie jak przy 96 różnych
plikach. Zawartość jest identyczna, więc wyniki dalej da się sprawdzić: zdarzeń ma być 96×,
a checksumy wszystkich biegów muszą się zgadzać. Rekord ma pole `cache` (`warm`/`cold`).

Zamiast rozgrzewania przez `cat` (przeczytałoby 1 TB na darmo) jest samosprawdzenie: skrypt
wyrzuca strony pierwszej kopii i pyta `fincore`, ile zostało. Jeśli zostały, przerywa, bo inaczej
każdy „zimny” pomiar byłby ciepły. `fincore` to util-linux ≥ 2.31; jak go nie ma, leci tylko
ostrzeżenie. Trzy odrzucane biegi `warmup_*` idą wtedy na jednej kopii — są po biblioteki i PCH,
nie po dane, więc trwają sekundy. MEMFS tu nie pomoże: ma 120 GB, więc 1 TB się nie zmieści (skrypt to odrzuci), a do
tego zabierałby RAM ścieżkom Python i uproot i dawałby odczyt najcieplejszy z możliwych.

Domyślnie 1 powtórzenie (`REPEATS_*=1`), bo samo skalowanie silne to tu ~2 h, więc na wykresach
nie będzie wąsów.

**Co się mierzy.** Tylko to, czego `ds_x32` nie mógł pokazać. `TESTS` wybiera eksperymenty;
dla `big` domyślnie `TESTS="strong weak qstruct size"` (zadanie A), a zadanie B to
`TESTS=sizepy`. Każde zaczyna się od 3 rozgrzewek.

| `TESTS` | test | wejście | biegów | ~czas | zadanie |
|---|---|---|---:|---:|---|
| `strong` | T1 skalowanie silne, wątki off, 1–48 | 96 kopii, ~1 TB | 30 | 2.2 h | A |
| `weak` | T2 skalowanie słabe, N wątków | 2N kopii, do ~1 TB | 21 | 0.5 h | A |
| `qstruct` | T4 lazy / eager / `Report()` × 1, 3, 5, jeden wątek | `lists/impl.txt`, ~98 GB | 9 | 15 min | A |
| `size` | T5 względem rozmiaru: RDF i uproot, jeden rdzeń | 1–9 kopii, ~11–98 GB | 36 | 30 min | A |
| `sizepy` | T5 względem rozmiaru: Python, jeden rdzeń | 1–9 kopii, ~11–98 GB | 18 | 9 h | B |
| `impl`, `slim`, `weakslim` | T5 na jednym wejściu, T6, T2S | — | — | — | pominięte |

T4 biegnie na ~100 GB, a nie na 1 TB, bo `rdf-eager` czyta wejście do 6 razy. T5 jest tu serią
rozmiarów, bo Python i uproot trzymają całe kolumny w pamięci i na 1 TB by padły. T6 i T2S nie
zależą od rozmiaru wejścia. Serie `size` i `sizepy` mają te same warianty co wykres 08: filtr
`rdf`, `uproot`, `python --mode loop`; łańcuch `rdf-lazy`, `uproot`, `python`; efektywność
`jit`, `uproot`, `python --mode loop`. Etykiety to `r1_size_<test>_<impl>_c<N>`, gdzie N to
liczba kopii.

**Python osobno i na końcu.** Łańcuch w Pythonie to ~16 min i ~16.6 GB RSS na kopię, więc na
8–9 kopiach potrzebuje ~133–150 GB z ~184 GB węzła. `sizepy` biegnie od najmniejszego rozmiaru,
najpierw filtr i efektywność, a łańcuch na samym końcu. Jeśli zabraknie pamięci, jądro zabija
tylko ten jeden proces. `run_one` zapisuje go jako `"status": "failed"` (kod 137) i kampania idzie
dalej, a wszystko wcześniej jest już w `raw.jsonl`. Wariant, który padł na N kopiach, nie jest
uruchamiany na większych: dostają rekord `failed` z `skipped_after` = N, bo i tak by padły po
nawet ~2 h czytania. Slurm może pokazać stan `OUT_OF_MEMORY`, ale wyniki zostają.
`RUN_TIMEOUT=14400` mieści łańcuch w Pythonie na 9 kopiach (~2.5 h).

Do pracy jedna uwaga: „1 TB” to rozmiar plików, a pętla czyta z nich tylko używane gałęzie —
od ~5 GB przy jednym wątku do ~90 GB przy 48 (`bytes_loop` rośnie z liczbą wątków, bo każdy
czyta własny nagłówek drzewa).

`$SCRATCH` jest czyszczony po ~30 dniach, więc wyniki skopiuj do `$PLG_GROUPS_STORAGE/<grant>/`.
`MaxRSS` z `sacct` (na końcu logu) powinien zgadzać się z `time_maxrss_kb` w `bench.csv`.

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
python test/merge_results.py --base results/helios/full-1tb-job1 \
    --add results/helios/full-1tb-job2 --shift 1 \
    --out results/helios/full-1tb
THREAD_SCALE=linear python test/plot_results.py --results results/helios/full-1tb
```

`THREAD_SCALE=linear` daje liniową oś wątków: przy siatce do 192 wątków zakres 96–192, gdzie leży
maksimum, zajmuje połowę osi, a nie jedną czwartą jak na osi logarytmicznej.

Optimum względem rozmiaru, po skopiowaniu wyników na laptopa:

```bash
python test/plot_optimum.py --results results/helios/full-{11m,100m,355m,1tb} \
    --out results/helios/full-1tb --tests chain
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

Zadanie 0 (`test/slurm_slim11_build.sbatch`, ~1–2 h, bez `--exclusive`):
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
THREAD_SCALE=linear python test/plot_results.py --results results/helios/slim-1.5tb
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

## Uruchomienie lokalnie

```bash
brew install coreutils gnu-time      # macOS: gtime i gtimeout, inaczej brak limitu i CPU%
python test/validate.py --threads 4
THREADS_LIST="1 2 4 8" WEAK_SERIES="1 2 4 8" REPEATS_STRONG=1 DATA_DIR=... ./test/run_benchmark.sh
python test/plot_results.py --results test/results
```

Skrypty same wybierają `.venv/bin/python`, jeśli istnieje; inny interpreter ustawisz przez `PY=`.
Domyślnie T1, T4 i T5 używają `ds_x32`, a ścieżka pythonowa materializuje całe kolumny
(~16 GB RSS), więc na laptopie z małą ilością RAM-u T5 wejdzie w swap. `DS_CORE=... DS_IMPL=...`
pozwala podać mniejsze wejście.

## Wyniki

Katalogi w `results/` (wszystkie wejścia czytane z dysku po wyczyszczeniu page cache, poza
archiwum):

| katalog | maszyna | dane | testy |
|---|---|---|---|
| `helios/full-1tb` | Helios | 96 kopii `ds_x32`, 1,07 mld zdarzeń, 1,04 TB | T1 do 192, T2 do 96; połączone `full-1tb-job1` i `full-1tb-job2` |
| `helios/full-1tb-job1` | Helios | jak wyżej | pierwsze zadanie: T1 1–192, T2 1–96 |
| `helios/full-1tb-job2` | Helios | jak wyżej | drugie zadanie: T1 64–192, 3 powtórzenia |
| `real-1/results-helios-opendata-1tb` | Helios | Run 2 Open Data (Run2016H, potem G), 653 pliki, 1,05 mld zdarzeń, ~1 TB, LZMA:9 | łańcuch `--period 2016`: T1 1–192 (r1; r2 i r3 z zadania 3); `15_real_vs_synthetic.png` |
| `real-1/results-helios-control-1tb` | Helios | jak `full-1tb`, w tym samym zadaniu co `opendata-1tb` | łańcuch: T1 na 1, 48, 144, 192 |
| `real-1/results-helios-opendata-weak4` | Helios | Open Data, `weak_4.txt`, ~87 mln zdarzeń | łańcuch `--period 2016`: T1 1–192, 3 powtórzenia (zadanie 3) |
| `real-1/results-helios-opendata-weak16` | Helios | Open Data, `weak_16.txt`, ~350 mln zdarzeń | jak wyżej |
| `real-1/results-helios-memtest` | Helios | 384 × `ds_x32_head.root` (1/32 `ds_x32`, 1984 gałęzie), z page cache | łańcuch: T1 na 1, 8, 32, 96, 192; `layout-*/dataset.json` (zadanie 3) |
| `helios/full-11m` | Helios | `ds_x32`, 11,1 mln zdarzeń | T1 do 192, 3 powtórzenia |
| `helios/full-100m` | Helios | 9 kopii, 99,9 mln zdarzeń | T1 do 192, 2 powtórzenia |
| `helios/full-355m` | Helios | 32 kopie, 355 mln zdarzeń | T1 do 192 |
| `helios/slim-1.5tb` | Helios | 96 plików slim (10 gałęzi), 29,8 mld zdarzeń, 1,54 TB | łańcuch 11 filtrów: T1 do 192, T2 do 96 |
| `ares/single-core` | Ares | 1–9 kopii (do 99,9 mln) i 1 TB | seria rozmiarów i implementacji, T4 na 99,9 mln; T1/T2 na 1 TB do 48 |
| `archive/ares-10gb-cached` | Ares | `ds_x1`–`ds_x32` i kopie slim, dane w page cache | dawna kampania 10 GB; nieużywana w pracy |

| plik | co pokazuje | test |
|---|---|---|
| `01_speedup_amdahl.png` | przyspieszenie vs wątki, dopasowanie Amdahla | T1 |
| `02_parallel_efficiency.png` | efektywność równoległa [%] | T1 |
| `03_weak_scaling.png` | czas przy stałej pracy na wątek z dopasowaniem `w + c·N`, przyspieszenie skalowane; slim przerywaną | T2, T2S |
| `04_rss_vs_threads.png` | koszt pamięciowy wątku | T3 |
| `05_rss_vs_size.png` | RSS wzdłuż serii słabej | T3 |
| `06_rss_over_time.png` | profil RSS w czasie, po krzywej na liczbę wątków | T3 |
| `07_query_structure.png` | liczba pętli po zdarzeniach i jej koszt | T4 |
| `08_implementations.png` | zdarzenia/s z liczbą zajętych rdzeni w pętli przy każdym słupku (i „pinned”) oraz rozbicie na fazy, osobno filter/chain/efficiency | T5 |
| `09_speedup_baselines.png` | przyspieszenie względem `ImplicitMT(1)` i względem wersji bez MT | T1 |
| `10_cores_busy.png` | ile rdzeni pracowało w pętli, pełny plik i slim | T1, T6 |
| `11_file_width.png` | czas pętli, przyspieszenie i RSS: pełny schemat vs slim | T6 |
| `13_input_size.png` | szczyt RSS i czas całkowity (setup + JIT + pętla) względem rozmiaru wejścia w GB, RDF / uproot / Python | `size`, `sizepy` |
| `14_optimum_vs_size.png` | optymalna liczba wątków względem liczby zdarzeń, z kilku katalogów wyników (`plot_optimum.py`): dopasowane $n^*=\sqrt{a/b}$ z $T(n)=c+a/n+b\,n$, najszybszy zmierzony punkt z plateau 5%, linia $\propto\sqrt{N}$ i liczba rdzeni maszyn; Open Data (`--period 2016`) jako osobna seria trójkątów | T1 |
| `15_real_vs_synthetic.png` | łańcuch na ~1 TB: czas pętli, przyspieszenie i RSS, zbiór sztuczny, kontrola i Open Data (`plot_real_vs_synthetic.py`, obok `summary_real_vs_synthetic.csv`) | T1 |
| `16_memory_layout.png` | szczyt RSS względem wątków dla kilku układów pliku i nachylenie (MB/wątek) względem koszyków na plik, z modelem $a + b\cdot\text{gałęzie} + c\cdot\text{koszyki}$ (`plot_memory_layout.py`, obok `summary_memory_layout.csv`) | T1 |

Przy `DATASET=big` nie ma biegów T5, więc wykres 08 powstaje z największego punktu serii
rozmiarów (9 kopii, ~98 GB). Na konsolę trafiają też nachylenia z serii (GB RSS i sekundy na
1 GB wejścia) oraz rozmiar, od którego RDF jest w sumie szybszy od uproot.

Wąsy na wykresach 01–04 i 09–11 to min–max z powtórzeń, punkt to mediana.

Obok wykresów powstaje `table_scalability_<test>.tex` (`filter`, `chain`, `efficiency`), czyli
tabela skalowalności z pracy (`tab:scalability`) liczona z T1: czas pętli przy `ImplicitMT(n)`,
czas całego procesu, przepustowość, przyspieszenie i efektywność względem `ImplicitMT(1)` oraz
„cores busy”, czyli CPU samej pętli przez jej czas. Przepustowość, przyspieszenie i efektywność
liczone są z czasu pętli. Czas całego procesu (z GNU time) obejmuje start Pythona i ROOT-a,
otwarcie plików i JIT: na 1 TB pełnych plików to ~24 s stałego kosztu przy pętli 13 s, na zbiorze
slim ~5 s przy 334 s. Podpis sam podaje liczbę zdarzeń, liczbę powtórzeń, zimny odczyt i maksimum.

`summary_strong_<test>.csv` to podsumowanie tego samego dla każdej zmierzonej liczby wątków
(nie tylko `TABLE_THREADS`): liczba biegów, mediana, minimum i maksimum czasu pętli, czas całego
procesu, stały koszt (setup, rozgrzewka, JIT), przepustowość, przyspieszenie, efektywność
i „cores busy”. Biegi pominięte przez regułę `OUTLIER_FACTOR` nie wchodzą do żadnej z tych
liczb. Rekordy sprzed poprawki parsera GNU time gubiły godziny w `elapsed_s` (bieg 8,6 h
zapisany jako 34 min); `plot_results.py` je odtwarza, bo proces trwa zawsze dłużej niż jego fazy,
a różnica to sekundy.
Powstaje też przy `--csv-only`.

Na konsolę trafiają też: frakcja szeregowa $s$ z Amdahla i **zmierzony** udział setup + JIT
przy jednym wątku. Jeśli dopasowane $s$ jest wyraźnie większe od zmierzonego, degradacja ma
przyczynę poza kodem szeregowym (optimum liczby wątków liczy `plot_optimum.py`). Dalej: koszt na wątek z T2 i T2S (ms/wątek), najlepsze
przyspieszenie względem wersji bez MT, RSS na wątek dla obu plików z T6 oraz sprawdzenie, że
wszystkie biegi T1 i T6 danego testu dały ten sam wynik (checksumy). „per extra thread”
podaje nachylenia RSS, odczytu i CPU pętli względem liczby wątków dla T1 i T6, a „T5 … against
T1 t0” różnicę między identycznymi biegami RDF z T5 i z T1.

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `DATASET` | `synthetic` | `synthetic` (`ds_xN`), `real` (listy z `make_filelists.py`) albo `big` (kopie z `make_bigset.sh`) |
| `DATA_DIR` | `test/data` | katalog z wejściami |
| `DS_CORE` / `DS_IMPL` / `DS_SLIM` | zależnie od `DATASET` (tabela w „Dane”) | wejścia T1 / T4–T5 / T6 |
| `WEAK_PATTERN` | `ds_x%s.root` / `weak_%s.txt` | wejście T2, `%s` = N |
| `WEAK_SLIM_PATTERN` | `ds_x%s_slim.root` / `weak_%s_slim.txt` | wejście T2S, tworzone automatycznie |
| `PIN_CORE` | `2` | rdzeń, do którego `taskset` przypina T5 (bez `taskset`: bez przypięcia, z ostrzeżeniem) |
| `RESULTS` | `test/results` (w `slurm_benchmark.sbatch`: `$SCRATCH/bench/results-$MACHINE[-big\|-real]`) | katalog wyjściowy |
| `MACHINE` | `local` (w `slurm_benchmark.sbatch`: `ares`) | trafia do każdego rekordu |
| `THREADS_LIST` | `1 2 4 8 12 16 24 32 48` | sweep wątków w T1 i T6 |
| `THREAD_SCALE` | `linear` przy siatce do ≥96 wątków, inaczej `log` | skala osi wątków (i osi przyspieszenia) w `plot_results.py` |
| `TABLE_THREADS` | `1 2 4 8 12 16 24 32 48 64 80 88 96 104 112 128 144 160 176 192` | wiersze tabel `table_scalability_*.tex` w `plot_results.py`; najszybszy punkt jest dokładany zawsze |
| `OUTLIER_FACTOR` | `1.5` | `plot_results.py` i `plot_optimum.py` pomijają bieg, którego pętla trwa dłużej niż tyle razy mediana tej samej konfiguracji (co najmniej 3 biegi); `0` wyłącza |
| `WEAK_SERIES` | `1 2 4 8 16 32` / `1 2 4 8 16 32 48` | N w T2 |
| `WEAK_UNIT` | `2` | kopii na wątek w punkcie T2 (tylko `big`): `weak_N.txt` ma `WEAK_UNIT`·N kopii |
| `CHAIN_LENS` | `1 3 5` | długości łańcucha w T4 |
| `TESTS` | wszystkie / `strong weak qstruct size` dla `big` | które eksperymenty biegną; `strongchain` to sam T1 łańcucha 5 filtrów (bez t0) |
| `CHAIN_ARGS` | — | dodatkowe argumenty `bench_chain.py` w `strongchain`, np. `--period 2016` |
| `SIZE_SERIES` | `1 2 4 6 8 9` | liczby kopii w `size` i `sizepy` (tylko `big`) |
| `BIG_COPIES` / `IMPL_COPIES` | `96` / `9` | ile kopii `ds_N.root` ma `lists/core.txt` / `lists/impl.txt` (tylko `big`) |
| `RESUME` | — | `1` dopisuje do `raw.jsonl` i pomija biegi, które są już `ok` |
| `REPEATS_STRONG` / `_WEAK` / `_QSTRUCT` / `_IMPL` / `_SLIM` | `5` / `3` / `2` / `3` / `3` | powtórzenia (mediana, wąsy min–max) |
| `RUN_TIMEOUT` | `2400` (w `slurm_benchmark.sbatch` dla `big`: `14400`) | limit na bieg [s] |
| `VALIDATE_THREADS` | `8` | liczba wątków w teście 1 vs N w `run_all.sh` |
| `SAMPLE_INTERVAL` | `0.1` | okres próbkowania RSS [s] |
| `DRY_RUN` | — | `1` wypisuje biegi bez uruchamiania |
| `PY` | `.venv/bin/python` lub `python3` | interpreter |

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów;
uruchom go po każdej zmianie w `POT_CONFIG` lub `get_cpp_source`. Cling nie pozwala
redefiniować funkcji w tym samym procesie, więc zmiany kernela sprawdzaj w świeżym procesie.
