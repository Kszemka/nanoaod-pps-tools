# Uruchomienie benchmarku na Ares / Helios

Co jest mierzone i dlaczego — patrz [TESTING.md](TESTING.md). Ten plik opisuje wyłącznie
uruchomienie.

Kampania nazywa się `core` i składa się z czterech eksperymentów na `ds_x32` — skalowanie
silne (Amdahl, USL), skalowanie słabe (Gustafson), struktura zapytania i porównanie
implementacji. Pamięć nie jest osobnym eksperymentem, tylko analizą danych zbieranych przez
dwa pierwsze. Szczegóły w [sekcji 5](#5-pełny-bieg). Poprzednia kampania (`full`, dziewięć
sweepów o układzie pliku, klastrowaniu i RNTuple) jest nadal w skrypcie i odtwarza wyniki
opisane w [RESULTS.md](RESULTS.md).

## Szybki start lokalnie

macOS nie ma GNU `time` ani `timeout`; bez nich odpadają peak RSS z `/usr/bin/time -v`, CPU%
i twardy limit na bieg (zostaje tylko `getrusage`). Warto je doinstalować:

```bash
brew install coreutils gnu-time     # daje gtime i gtimeout
```

```bash
cd test
python validate.py --max-events 40000     # poprawność przed jakimkolwiek pomiarem
./run_benchmark.sh quick                  # smoke test na examples/test.root
python plot_results.py
```

Diagnostyka I/O osobno — mówi nie „ile bajtów", ale dlaczego tyle (liczba wywołań read,
bajty odczytane ponad to, o co poproszono, sweep rozmiaru `TTreeCache`):

```bash
python diag_io.py --input ../examples/test.root --cache-mb 0 30 128
```

Skrypty same wybierają `.venv/bin/python` z korzenia repo, jeśli istnieje, i od razu sprawdzają,
czy ten interpreter widzi ROOT. Wywołania pythonowe wprost (`validate.py`, `plot_results.py`)
uruchamiaj przez `.venv/bin/python`, chyba że masz aktywne środowisko — `python3` z `PATH` to
zwykle inny interpreter, bez PyROOT. Innym interpreterem sterujesz przez `PY=...`.

### Profil laptopowy

Domyślne wartości celują w węzeł obliczeniowy (48–192 rdzeni, 192+ GB RAM). Na laptopie trzeba
zejść z liczbą wątków i z rozmiarem danych — ścieżka pythonowa materializuje całe kolumny
w pamięci, więc to ona, a nie RDataFrame, wyznacza górny limit:

```bash
export THREADS_LIST="1 2 4 8 16"     # nie więcej niż rdzeni
export DS_CORE=$PWD/test/data/ds_x8.root   # ds_x32 nie zmieści się na laptopie
export WEAK_SERIES="1 2 4 8"          # ~2.5 GB danych, Python mieści się w RAM
export REPEATS_STRONG=1
```

Przy 24 GB RAM seria powyżej `x8` zaczyna wchodzić w swap na ścieżce pythonowej — pomiar czasu
staje się wtedy pomiarem dysku. `gtimeout` jest tu zabezpieczeniem, nie ozdobą.

## Krok po kroku na Cyfronecie

### 1. Logowanie i katalog roboczy

```bash
ssh <login>@ares.cyfronet.pl        # lub helios.cyfronet.pl
mkdir -p $SCRATCH/bench && cd $SCRATCH/bench
```

`$SCRATCH` jest czyszczony po ~30 dniach — gotowe wyniki skopiuj do
`$PLG_GROUPS_STORAGE/<grant>/`. `$HOME` ma limit ~10 GB, więc **nie** instaluj tam
środowiska.

### 2. Środowisko

Moduły Cyfronetu mają ROOT, ale nie mają `correctionlib`, więc potrzebne jest własne
środowisko:

```bash
cd $SCRATCH/bench
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
mkdir -p micromamba && mv bin micromamba/
export MAMBA_ROOT_PREFIX=$SCRATCH/bench/micromamba
eval "$(./micromamba/bin/micromamba shell hook -s bash)"

git clone <repo-url> nanoaod-pps-tools
micromamba env create -f nanoaod-pps-tools/test/environment.yml
micromamba activate pps-bench
```

### 2b. Git LFS

`examples/test.root` jest trzymany w Git LFS. Bez `git-lfs` klon daje w tym miejscu
134-bajtowy plik tekstowy ze wskaźnikiem zamiast 240 MB danych, a wszystko dalej wywala się
na nieczytelnym pliku ROOT. `environment.yml` instaluje `git-lfs`, więc po aktywacji
środowiska wystarczy:

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
git lfs install
git lfs pull
ls -la examples/test.root        # ma mieć ~240 MB, nie 134 B
```

`run_all.sh` sprawdza to sam i przerywa z czytelnym komunikatem, jeśli trafi na wskaźnik.

Alternatywa, jeśli LFS sprawia kłopoty: skopiuj plik wprost z laptopa —
`scp examples/test.root <login>@ares.cyfronet.pl:'$SCRATCH'/bench/nanoaod-pps-tools/examples/`.

Sprawdzenie:
`python -c "import ROOT, correctionlib, numpy, uproot, awkward; print(ROOT.gROOT.GetVersion())"`.

`uproot` i `awkward` nie są opcjonalne. Na nich stoi implementacja `uproot` — jedyna
porządnie kolumnowa ścieżka pythonowa w tym benchmarku. Bez niej stronę pythonową
reprezentuje tylko `AsNumpy`, którego koszt jest zdominowany przez to, że PyROOT tworzy
jeden obiekt na zdarzenie, więc główny stosunek RDataFrame-do-Pythona mierzyłby nie to, co
powinien (8.66 s vs 0.21 s na tym samym zapytaniu). `run_all.sh` przerywa, jeśli ich brak.

### 3. Dane

Kopie pliku źródłowego. `--autoflush` steruje liczbą klastrów TTree — **to on, a nie rozmiar
pliku, wyznacza górną granicę sensownego zrównoleglenia** (RDataFrame dzieli pracę po
klastrach, nie po zdarzeniach). Skrypt sam ostrzega, jeśli klastrów jest za mało.

Najprościej jednym poleceniem — każdy plik jest od razu opisywany w `dataset_info.json`:

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
DATA_DIR=$SCRATCH/bench/data ./test/make_all_datasets.sh
```

Powstaje **wyłącznie seria `ds_xN`** — 63 kopie, ~5.4 min każda:

| plik | kopii | zdarzeń | klastrów | rola |
|---|---:|---:|---:|---|
| `ds_x1` | 1 | 346 825 | 36 | T2 przy 1 wątku |
| `ds_x2` | 2 | 693 650 | 71 | T2 przy 2 wątkach |
| `ds_x4` | 4 | 1 387 300 | 140 | T2 przy 4 wątkach |
| `ds_x8` | 8 | 2 774 600 | 279 | T2 przy 8 wątkach |
| `ds_x16` | 16 | 5 549 200 | 556 | T2 przy 16 wątkach |
| `ds_x32` | 32 | 11 098 400 | 1111 | T2 przy 32 wątkach **oraz całe T1, T4 i T5** |

Jeden `autoflush` (10 000) w całej serii, inaczej klastrowanie stałoby się ukrytą drugą
zmienną i pierwszy punkt odstawałby od dopasowanej prostej.

Dlaczego `ds_x32`, a nie `ds_x8`: krzywa przyspieszenia jest warta tyle, ile długa jest pozycja
odniesienia. Na `ds_x8` pętla jednowątkowa trwa 4–11 s przy koszcie stałym 1.4–1.8 s, więc
punkty 32- i 48-wątkowe są obciążone w dół — mierzą narzut, nie skalowanie. Na `ds_x32` ta
pętla to ~44 s. Jego 1111 klastrów daje też zapas równoległości na ~277 wątków, więc 48 jest
daleko od granicy narzuconej przez klastrowanie.

Seria działa jako skalowanie słabe, bo **klastrów na wątek jest w niej stała liczba**: 36.0,
35.5, 35.0, 34.9, 34.75, 34.7 dla par (1,`ds_x1`) … (32,`ds_x32`). RDataFrame dzieli pracę po
klastrach, więc każdy wątek dostaje dokładnie tyle samo jednostek pracy — bez tego skalowanie
słabe nie byłoby uczciwe. `ds_x12` i `ds_x24` nie istnieją i nie są potrzebne: `WEAK_SERIES`
zostaje przy potęgach dwójki, a dodatkowe punkty 12 i 24 dotyczą wyłącznie `THREADS_LIST`
w T1, gdzie dataset się nie zmienia.

#### Pliki kontrolne starej kampanii (domyślnie **nie** powstają)

`WANT_CONTROLS=1` dokłada to, czego używała kampania `full`. Nie włączaj tego bez potrzeby:
to 56 kopii przy 63 kopiach samej kampanii, czyli podwojenie czasu generacji dla plików,
których `core` nie dotyka.

| plik | kopii | po co powstał | dlaczego nie jest już potrzebny |
|---|---:|---|---|
| `ds_s` | 1 | kopia źródła, LZMA:9 | inna kompresja niż reszta — nigdy nie był punktem żadnej serii |
| `ds_x8_coarse` | 8 | kontrola klastrowania (autoflush 250 000) | hipoteza obalona — zależność wyszła odwrotna |
| `ds_x8_slim` | 8 | kontrola amplifikacji odczytu (10 gałęzi zamiast 1984) | pytanie o układ pliku, nie o to oprogramowanie |
| `ds_x8_rntuple` | — | porównanie TTree vs RNTuple | pytanie o format ROOT-a, nie o to oprogramowanie |
| `ds_l` | 40 | jedyny plik z anomalią odczytu 10 GB | dodatkowo za `WANT_DS_L=1`; ~11 GB i najdłuższy element skryptu |

**`ds_l` nie bierze udziału w pomiarach czasu i nie powinien.** Zmierzone na Aresie: 36 biegów
przez 1.77 h, z czego 11 weszło w timeout i nie dało żadnego rekordu (0.92 h, ponad połowa
zadania). W biegach, które się skończyły, dominował koszt stały, nie pętla zdarzeń —
`efficiency/jit` to 290 s, z czego 202 s setupu i 84 s pętli. Godziny kupiły więc głównie
narzut. Został w skrypcie tylko dlatego, że na nim widać anomalię odczytu, którą bada
`diag_io.py` — diagnostyka tylko do odczytu, liczona w sekundach.

Para `ds_x8` / `ds_x8_coarse` musi mieć **identyczną liczbę zdarzeń** — inaczej objętość
udawałaby klastrowanie, czyli dokładnie to zakłócenie, które ta kontrola ma wykluczyć.
`run_benchmark.sh` sprawdza to i odmawia uruchomienia porównania, jeśli się różnią.

Liczby zdarzeń, klastrów, bajtów i rozmiarów koszyka per gałąź lądują w
`$SCRATCH/bench/data/dataset_info.json` — `plot_results.py` czyta stamtąd limit klastrów dla
**użytego** datasetu, żeby nanieść go na wykres skalowania. Dataset bez wpisu jest błędem
przerywającym pomiar: bez niego limit wątków i adnotacje brałyby liczby z innego pliku.

Kopiowanie pliku zwiększa rozmiar o ~20% względem `N × źródło`, bo mniejsze klastry gorzej się
kompresują. Kompresja jest dopasowywana do pliku źródłowego automatycznie.

**Czas generacji.** `make_all_datasets.sh` wymusza ZSTD:5 właśnie dlatego: przy LZMA:9 ze
źródła zapis jednej kopii zajmuje 156 s zamiast 70 s, więc cała seria potrafi zająć godziny.
Generuj datasety oddzielnym, długim zadaniem (nie w tym samym, co pomiary), np.:

`Snapshot` jest jednowątkowy, więc domyślny bieg zostawia 47 z 48 rdzeni bezczynnych na
godziny. Pliki są od siebie niezależne, więc `JOBS=N` buduje po N naraz i całość trwa tyle,
ile jej największy element, a nie tyle, ile ich suma:

```bash
JOBS=6 DATA_DIR=$SCRATCH/bench/data ./test/make_all_datasets.sh
```

Każdy bieg ma wtedy własny log w `$DATA_DIR/logs/`, bo sześć przeplecionych strumieni jest
nieczytelne dokładnie wtedy, gdy coś się wywali. Skrypt czeka na wszystkie przed konwersją
RNTuple (ta potrzebuje kompletnego `ds_x8`) i przerywa, jeśli którykolwiek build zawiódł.
```bash
sbatch -A <GRANT>-cpu -p plgrid-long -N1 -c8 --time=12:00:00 \
       --wrap "micromamba run -n pps-bench bash test/make_all_datasets.sh"
```

Alternatywa: `--compression 5:5` (ZSTD zamiast LZMA) skraca generację wielokrotnie. **Zmienia
jednak koszt dekompresji, czyli jedną z mierzonych wielkości** — jeśli jej użyjesz, użyj jej dla
*wszystkich* datasetów w serii i odnotuj to w opisie wyników. Nigdy nie mieszaj algorytmów
kompresji w obrębie jednego wykresu.

### 4. Test dymny na węźle obliczeniowym

Jako zadanie wsadowe, nie przez `srun --pty`: zerwane połączenie SSH zabija sesję
interaktywną razem z biegiem, a zakolejkowane zadanie liczy się dalej i zapisuje wyjście
do pliku.

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
sed -i "s/<GRANT>/twoj-grant/" test/slurm_smoke.sbatch
mkdir -p $SCRATCH/bench/logs
sbatch --output=$SCRATCH/bench/logs/smoke-%j.out \
       --error=$SCRATCH/bench/logs/smoke-%j.err \
       test/slurm_smoke.sbatch

squeue -u $USER                              # postęp
tail -f $SCRATCH/bench/logs/smoke-<jobid>.out
```

Ścieżek `$SCRATCH` nie da się użyć w dyrektywach `#SBATCH` (są czytane przed rozwinięciem
zmiennych powłoki), dlatego katalog logów podaje się w wierszu poleceń. Bez tego pliki
`smoke-<jobid>.out` lądują w katalogu, z którego wywołano `sbatch`.

Zadanie ma się skończyć linią `RESULT: all checks passed` i wypisaniem `bench.csv`.
Jeśli walidacja nie przechodzi, nie uruchamiaj pomiarów — żadna liczba nie będzie wtedy
nic warta.

Jeśli mimo wszystko wolisz sesję interaktywną, uruchom ją w `tmux`, żeby przeżyła
rozłączenie:

```bash
tmux new -s bench
srun -A <GRANT>-cpu -p plgrid-testing -N1 -n1 -c4 --time=0:30:00 --pty bash -l
# Ctrl-b d odłącza, `tmux attach -t bench` wraca
```

Warto też ograniczyć same rozłączenia — na laptopie w `~/.ssh/config`:

```
Host ares.cyfronet.pl
    ServerAliveInterval 60
    ServerAliveCountMax 10
```

### 5. Pełny bieg

Kampania `core` to cztery eksperymenty, wszystkie na jednym zbiorze, żeby żadne porównanie
w całym biegu nie rozkładało się na dwa pliki:

| | co zmienia | dataset | wątki | powtórki | biegów |
|---|---|---|---|---|---|
| **T1** skalowanie silne | liczbę wątków przy stałym problemie | `ds_x32` | 1–48 | 3 | 81 |
| **T2** skalowanie słabe | problem **i** wątki naraz | `ds_xN` | N | 3 | 54 |
| **T4** struktura zapytania | długość łańcucha i sposób jego zapisu | `ds_x32` | 1 | 2 | 18 |
| **T5** implementacje | RDF / correctionlib / Python / uproot | `ds_x32` | 1 | 1 | 12 |

**T1 pyta, czy tę samą robotę zrobię szybciej** — stąd przyspieszenie, efektywność równoległa
i dopasowanie prawa Amdahla wraz z jego rozszerzeniem USL (Universal Scalability Law, które
dokłada człon koherencji κ i jako jedyne potrafi opisać krzywą zawracającą w dół).
**T2 pyta, czy w tym samym czasie zrobię proporcjonalnie więcej roboty** — to prawo Gustafsona,
a ideałem jest tu płaska linia czasu, nie opadająca.

**T3 nie ma własnych biegów.** Pamięć to analiza danych, które T1 i T2 zbierają i tak: każdy
bieg zapisuje `peak_rss_kb` oraz ślad `rss_<label>.csv` próbkowany co 0.1 s. Stąd wykresy
RSS vs liczba wątków, RSS vs rozmiar problemu i profil RSS w czasie.

Poza nimi leci jeden bieg rozgrzewający `core_warmup`: `--exclusive` rezerwuje węzeł, ale nie
Lustre, więc bez niego pierwszy mierzony bieg niosłby cudze obciążenie I/O. Nie trafia na
żaden wykres.

Najpierw sprawdź, na co idą godziny grantu — `DRY_RUN` wypisuje każdy bieg, nie uruchamiając
żadnego. Liczby biegów nie da się policzyć z lektury skryptu, bo sweep wątków jest przycinany
w trakcie do liczby klastrów datasetu, a całe bloki są pomijane przy braku pliku:

```bash
DRY_RUN=1 ./test/run_benchmark.sh core | tail -3          # budżet: załóż, że wszystko istnieje
DRY_RUN=have ./test/run_benchmark.sh core | grep SKIP     # co wypadnie przy brakach na dysku
```

Drugi tryb jest ważniejszy przy niekompletnym zestawie danych. Punkty serii `weak`
**pomijają się po cichu**, jeśli brakuje `ds_xN` — bieg kończy się sukcesem, tylko krzywa
Gustafsona ma mniej punktów.

Na domyślnej konfiguracji kampania `core` to **166 biegów** (1 rozgrzewający + 81 + 54 + 18
+ 12) i **~2.1 h**, przy limicie 8 h w pliku sbatch. Najdroższy element to `chain/python`
z T5: ~1160 s na `ds_x32`, stąd `RUN_TIMEOUT_CORE=2400`.

Stara kampania (`full`, 250 biegów, dziewięć sweepów) jest nadal w skrypcie — odtwarza
`results-ares-new` i rozdziały RESULTS.md o układzie pliku, klastrowaniu i RNTuple.
Nie uruchamiaj obu do jednego katalogu wyników: `plot_results.py` rysuje jeden zestaw
wykresów albo drugi, a nie oba naraz.

Uzupełnij `<GRANT>` i partycję w plikach sbatch, a dla Heliosa dodatkowo `--cpus-per-task`
(patrz komentarz na górze pliku — specyfikację trzeba potwierdzić w aktualnej dokumentacji).

```bash
sbatch test/slurm_benchmark.sbatch           # Ares
sbatch test/slurm_benchmark_helios.sbatch    # Helios
```

`--exclusive` jest w obu skryptach celowo: na współdzielonym węźle wykres skalowania mierzy
obciążenie sąsiadów, nie własny kod.

Skrypt Aresa woła `run_all.sh` **bez `srun`**. Od Slurm 22.05 krok zadania nie dziedziczy
`--cpus-per-task` z alokacji, więc `srun` potrafił przydzielić całej kampanii jeden rdzeń —
a to nie wywala biegu, tylko spłaszcza krzywą przyspieszenia. Skrypt wsadowy i tak działa
w cgrupie obejmującej pełną alokację. Na wszelki wypadek na starcie wypisywane są `lscpu`,
`nproc` i affinity procesu, a gdy widocznych CPU jest mniej niż zamówiono, job **przerywa**
zamiast policzyć złe liczby.

### 6. Kontrola i odbiór wyników

Kampania `core` zostawia w katalogu wyników osiem wykresów:

| plik | co pokazuje | z testu |
|---|---|---|
| `01_speedup_amdahl.png` | przyspieszenie vs wątki, z dopasowaniem Amdahla i USL | T1 |
| `02_parallel_efficiency.png` | efektywność równoległa [%] | T1 |
| `03_weak_scaling.png` | czas przy stałej pracy na wątek + przyspieszenie skalowane vs Gustafson | T2 |
| `04_rss_vs_threads.png` | koszt pamięciowy jednego wątku | T3 |
| `05_rss_vs_size.png` | RSS wzdłuż serii słabej | T3 |
| `06_rss_over_time.png` | profil RSS w czasie, po jednej krzywej na liczbę wątków | T3 |
| `07_query_structure.png` | liczba pętli po zdarzeniach i jej koszt | T4 |
| `08_implementations.png` | przepustowość i rozbicie na fazy | T5 |

Do konsoli trafiają też liczby, których nie widać na wykresie: frakcja szeregowa $s$ z Amdahla
wraz z sufitem $1/s$, parametry $\sigma$ i $\kappa$ z USL, przewidywane optimum liczby wątków
oraz **zmierzony** udział części szeregowej (setup + JIT) przy jednym wątku. Te dwa ostatnie
warto porównać: jeśli dopasowane $s$ jest wyraźnie większe od zmierzonego, degradacja ma
przyczynę poza własnym kodem szeregowym — i wtedy mówi o niej dopiero $\kappa$.

Stara kampania `full` rysuje swój własny zestaw `01_…12_`. `plot_results.py` wybiera jeden
zestaw albo drugi na podstawie etykiet w `raw.jsonl`, więc **nie mieszaj obu kampanii w jednym
katalogu wyników**.

```bash
sacct -j <jobid> --format=JobID,JobName,State,Elapsed,MaxRSS,AveCPU,NCPUS,ReqMem
```

(`seff` nie jest zainstalowany na Aresie.)

`MaxRSS` z `sacct` powinien zgadzać się z kolumną `time_maxrss_kb` w `results/bench.csv` —
to niezależne potwierdzenie, że pomiar pamięci jest poprawny.

```bash
cp -r $SCRATCH/bench/results-* $PLG_GROUPS_STORAGE/<grant>/
scp -r <login>@ares.cyfronet.pl:$PLG_GROUPS_STORAGE/<grant>/results-ares .
```

Wykresy z obu maszyn razem:

```bash
mkdir -p combined && cat results-ares/raw.jsonl results-helios/raw.jsonl > combined/raw.jsonl
cp results-ares/dataset_info.json combined/
cp results-*/rss_*.csv combined/        # wykres profilu pamięci czyta je z katalogu wyników
python test/plot_results.py --results combined
```

Scalanie jest bezpieczne tylko w obrębie tej samej wersji schematu. Każdy rekord nosi
`schema_version`, a `plot_results.py` odrzuca starsze i mówi ile — część pól zmieniła
znaczenie (`n_events` w TEŚCIE 3, podział czasu między fazy), więc uśrednienie rekordów
z dwóch wersji dałoby liczby nienależące do żadnej z nich.

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `MACHINE` | `local` | trafia do każdego rekordu; rozróżnia Ares od Heliosa na wykresach |
| `DATA_DIR` | `test/data` | katalog z datasetami |
| `RESULTS` | `test/results` | katalog wyjściowy |
| `THREADS_LIST` | `1 2 4 8 12 16 24 32 48` | sweep wątków w T1 |
| `DS_CORE` | `$DATA_DIR/ds_x32.root` | dataset kampanii `core` |
| `WEAK_SERIES` | `1 2 4 8 16 32` | pary (N wątków, `ds_xN`) dla skalowania słabego |
| `CHAIN_LENS` | `1 3 5` | długości łańcucha w T4 |
| `REPEATS_STRONG` / `_WEAK` / `_QSTRUCT` / `_IMPL` | `3` / `3` / `2` / `1` | powtórzenia per eksperyment (mediana, wąsy min–max) |
| `RUN_TIMEOUT_CORE` | `2400` | limit na bieg w kampanii `core` |
| `REPEATS` | `3` | powtórzenia w starej kampanii `full` |
| `RUN_TIMEOUT` | `300` | limit na bieg poza kampanią `core` |
| `DS_MAIN` | `$DATA_DIR/ds_x8.root` | główny dataset starych sweepów (`DS_L` działa jako alias) |
| `DS_S` | `$DATA_DIR/ds_x1.root` | dataset ścieżek jednowątkowych w kampanii `full` |
| `DS_COARSE` | `$DATA_DIR/ds_x8_coarse.root` | druga połowa pary kontrolnej klastrowania (`full`) |
| `SCALE_SERIES` | `1 2 4 8 16 32` | seria rozmiarowa starej kampanii (`cmd_scaling`) |
| `BENCH_INPUT` | — | tryb jednego datasetu dla kampanii `full`; na `core` nie działa — tam służy do tego `DS_CORE` |
| `DRY_RUN` | — | `1` = wypisz plan zakładając, że wszystkie datasety istnieją; `have` = tylko to, co pozwalają pliki na dysku |
| `WANT_CONTROLS` | `0` | `1` dokłada pliki kontrolne starej kampanii (`ds_s`, `_coarse`, `_slim`, `_rntuple`) |
| `WANT_DS_L` | `0` | `1` dokłada `ds_l` (40 kopii, ~11 GB); wymaga też `WANT_CONTROLS=1` |
| `JOBS` | `1` | ile datasetów generować równolegle (`make_all_datasets.sh`) |
| `SERIES` | `1 2 4 8 16 32` | liczby kopii w serii `ds_xN` |
| `SAMPLE_INTERVAL` | `0.1` | okres próbkowania RSS (sekundy) |
| `PY` | `python3` | interpreter |

Bieg, który przekroczy limit czasu (`RUN_TIMEOUT_CORE` w kampanii `core`, `RUN_TIMEOUT` poza
nią), jest zapisywany jako `"status": "failed"` wraz
z wartością limitu, a `plot_results.py` **rysuje go jako dolne ograniczenie** — granica
wydajności implementacji też jest wynikiem i ma być widoczna na wykresie, nie tylko w danych.

Profil pamięci (`rss_<label>.csv`) próbkuje **sam proces mierzony**, przez wątek daemon
czytający `/proc/self/statm`. Wcześniej próbkował go bash przez `ps -p $!`, ale komenda jest
owinięta w `timeout` i `/usr/bin/time`, więc `$!` było pidem opakowania: wszystkie zebrane tak
ślady to płaska linia na poziomie ~1.1 MB, czyli rozmiar samego `timeout`.

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów.
To jedyne zabezpieczenie przed cichym błędem transkrypcji geometrii — uruchom je po każdej
zmianie w `POT_CONFIG` lub w `get_cpp_source`.

Uwaga: cling nie pozwala redefiniować raz zadeklarowanej funkcji w tym samym procesie.
Zmiany w kernelu weryfikuj w świeżym procesie, nie przez ponowne uruchomienie komórki
w żywym kernelu notebooka.
