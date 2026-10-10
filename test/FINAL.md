# Ostateczna kampania: łańcuch 11 filtrów na Heliosie

Ostatni pomiar do pracy: jedno zadanie `slurm_final.sbatch` na `plgrid-now` (jeden węzeł,
192 rdzenie, 384 000 MB, 12 h; QoS pozwala na jedno zadanie użytkownika, licząc oczekujące).
W `test/` są tylko pliki tego zadania i analizy jego wyników; reszta jest w
[`archive/`](archive/README.md).

## Łańcuch

11 filtrów na 10 gałęziach (`bench_spec.LONG_CHAIN_STEPS`), krótkie spięcie RDataFrame:

```
theta_y, multi_proton, multi_rp_idx, single_rp_idx, track_x, track_y,
pps, double_arm, diamond, rp_id, xi
```

`track_x` i `track_y` to `PPSLocalTrack_x > 4` i `PPSLocalTrack_y > 0` (jakiś ślad w zdarzeniu),
takie same w okresach `2016`, `run3` i `2026`. Zastępują `time == 0` i `timeUnc == 0`: piksele
(Run 3) i paski (2016) czasu nie mierzą, więc tamte dwie gałęzie były czytane, a cięcie na nich
nic nie wybierało. Progi są luźne, żeby łańcuch zostawiał dużo zdarzeń (y na paskach leży wokół
zera, więc `y > 4` odrzuciłoby cały 2016).

Każdy rekord `raw.jsonl` ma pole `chain_cuts`, np. dla Run 3:

```
theta_y,multi_proton,multi_rp_idx==-1,single_rp_idx>=0,track_x>4,track_y>0,pps,double_arm(23|123)&(3|103),diamond==4,rp_id==23,xi[0.05,0.1]
```

a `check_chain11.py` wypisuje je w pierwszej linii, więc wyniki z innymi cięciami da się
rozpoznać (i kroki same je odsuwają, niżej).

Zbiory już zmierzone zostają: slim (`results/synthetic-slim`) i Block M
(`results/full-chain11/artificial-1tb`) mają jeszcze `time`/`timeUnc`: tyle samo gałęzi i ta
sama reszta łańcucha; w pracy jedno zdanie, że 2 z 10 gałęzi są tam inne. Model kosztu otwartego
drzewa z Block M nie zależy od tego, które gałęzie są czytane.

## Kroki

| krok | co | wynik na `$SCRATCH/bench` | szacunek |
|---|---|---|---|
| `gate` | `check_chain11.py --period 2016` na każdym pliku Run 2 (`data2/local.csv`), 96 procesów | `run2_chain11_gate.{txt,status}`, `run2_chain11.csv` | ~5 min |
| `gate3` | `check_chain11.py --period run3` na każdym pliku Run 3 (`data3/local.csv`) | `run3_chain11_gate.{txt,status}`, `run3_chain11.csv` | 5–10 min |
| `J1` | `strong11` na Run 3 `core.txt`, `--period run3`, 1–192 wątki, 80–192 trzy razy | `results-helios-run3-chain11` | 3–4 h |
| `J3` | `node11`: RDF na 192 wątkach i `uproot-pool` na 192 procesach, po 3 biegi | `results-helios-run3-node` | ~1 h |
| `R` | `strong11` na Run 2 Open Data `core.txt`, `--period 2016`, jak J1 | `results-helios-run2-chain11-1tb` | ~1 h |
| `J4` | `node11`: `python-pool` na 192 procesach, 3 biegi, każdy najwyżej 1,5 h | `results-helios-run3-node` | 1–4,5 h |

Razem ~6–9 h. R idzie tylko po `gate` z kodem 0, J1, J3 i J4 tylko po `gate3` z kodem 0. Kody
bramki: 2 kolumna z dwoma typami, 3 plik, którego łańcuch nie przeczyta, 4 łańcuch, po którym w
całym zbiorze nie zostaje nic. Przepływ po erach jest w `.txt` bramki.

J4 jest ostatni: brak czasu albo pamięci kosztuje tylko J4. Pule (`bench_pool.py`) dostają
kawałki plików po `POOL_CHUNK_EVENTS` (250 000) zdarzeń, a nie całe pliki: przy 192 procesach i
plikach Run 3 do ~1,35 mln zdarzeń całe pliki w pamięci nie zmieściłyby się w 384 GB. Bieg po
timeoucie (kod 124) nie jest powtarzany, także po wznowieniu; w pracy jako dolne ograniczenie.

„R na czysto”: katalog wyników R z rekordami innych cięć (stary R miał łańcuch z `time`) krok
odsuwa jako `results-helios-run2-chain11-1tb-oldcuts-<data>` i mierzy od nowa, przy spokojnym
Lustre, bez `--best-of`. J1 i `results-helios-run3-node` tak samo.

## Listy Run 3 (raz, przed kampanią)

Pliki Run 3 są w `$SCRATCH/bench/data3/data`, ich spis z EOS w `data3/run3_sizes.txt`. Listy
(`local.csv`, `core.txt`, `impl.txt`, `sets.json`, `READY`) robi osobne zadanie na `plgrid`
(16 CPU, do 6 h), bez połączenia z CERN:

```bash
cd $SCRATCH/bench/nanoaod-pps-tools && git pull
sbatch test/archive/slurm_fetch_eos.sbatch      # OUT_DIR domyślnie $SCRATCH/bench/data3
cat $SCRATCH/bench/data3/READY                  # po zadaniu
```

Kroki: rozmiar każdego pliku z `run3_sizes.txt` (brak choć jednego kończy zadanie),
inwentaryzacja (`local.csv`), łańcuch z `--period run3` na każdym pliku (przepływ po erach do
`READY`), listy, `READY`. Do list idzie każdy plik, który da się otworzyć i ma 10 gałęzi
łańcucha, tak jak analiza bierze całą listę plików: bez wyboru po udziale PPS ani po tym, czy
łańcuch coś zostawia (`MIN_PPS`, `MIN_PASSED`, domyślnie 0). Każdy krok z gotowym wynikiem jest
pomijany, więc po przerwaniu wystarczy wysłać je jeszcze raz.

## Uruchomienie

```bash
cd $SCRATCH/bench/nanoaod-pps-tools && git pull
squeue -u $USER                       # nic innego nie biegnie ani nie czeka
hpc-fs                                # scratch jest czyszczony po ~30 dniach
head -1 $SCRATCH/bench/data3/READY
ls -l $SCRATCH/bench/data2/core.txt $SCRATCH/bench/data2/local.csv
DRY_RUN=1 bash test/slurm_final.sbatch   # kroki i brakujące wejścia
sbatch test/slurm_final.sbatch
```

Śledzenie: `squeue -u $USER`, `tail -f bench-final-<id>.out`,
`cat $SCRATCH/bench/final_progress.log` (po każdym kroku linia: kod wyjścia, czas, liczba
rekordów `ok` i nieudanych). Do końca zadania nie robić `git pull`.

## Wznawianie

Wyniki idą na Lustre, a każdy bieg jest dopisywany do `raw.jsonl` zaraz po końcu, więc przy
awarii albo po 12 h przepada tylko bieg, który właśnie trwał. Po przerwaniu ta sama komenda:

```bash
sbatch test/slurm_final.sbatch
```

- Krok, który skończył się kodem 0 bez nieudanych biegów, zapisuje
  `$SCRATCH/bench/final_state/<krok>.done` z podpisem cięć i przy ponownym wysłaniu jest
  pomijany od razu.
- Pozostałe biegną z `RESUME=1`: pomijają etykiety zapisane jako `ok`.
- Bramka zapisana z bieżącymi cięciami nie liczy się drugi raz.
- Jeden krok od nowa: usunąć jego `final_state/<krok>.done` (bramkę: także `.status`).
  Tylko część kroków: `sbatch --export=ALL,STEPS="R J4" test/slurm_final.sbatch`.

## Po zadaniu

Na laptopie (polecenia też w [`results/README.md`](../results/README.md)):

```bash
rsync -a helios:'$SCRATCH/bench/results-helios-run2-chain11-1tb/' results/full-chain11/run2-1tb/
rsync -a helios:'$SCRATCH/bench/results-helios-run3-chain11/'     results/run3/chain11/
rsync -a helios:'$SCRATCH/bench/results-helios-run3-node/'        results/run3/node/
scp helios:'$SCRATCH/bench/run2_chain11_gate.txt' results/full-chain11/run2-1tb/
scp helios:'$SCRATCH/bench/run3_chain11_gate.txt' results/run3/chain11/
scp helios:'$SCRATCH/bench/final_progress.log'    results/run3/
python test/plot_results.py --results results/run3/chain11
python test/plot_results.py --results results/run3/node      # wykres 17: RDF / uproot / Python
```

Potem porównanie zbiorów (`plot_real_vs_synthetic.py`, bez `--best-of` dla Run 2) i Block M
(`plot_memory_control.py`), komendy w `results/README.md`. W pracy: opis łańcucha (x, y zamiast
czasu; zdanie o slim i Block M), J1 zamiast tymczasowego Run 3 z cięciami 2026, J3 i J4 w bloku N,
przepływ po erach z obu bramek.

## Pliki

„Zmieniony” to zmiana w tej ostatniej rundzie (x/y, podpis cięć, kawałki w pulach, J4, bramka
Run 3, wznawianie).

| plik | rola | zmieniony |
|---|---|---|
| `slurm_final.sbatch` | całe zadanie: kroki, bramki, odsuwanie wyników innych cięć, `final_progress.log`, `.done` | tak |
| `slurm_run3.sbatch` | kroki J1, J3, J4 (`JOB=`): `validate.py`, `dataset_json.py`, `run_benchmark.sh` | tak (`POOL_CHUNK_EVENTS`) |
| `slurm_benchmark.sbatch` | krok R: cały węzeł, `run_all.sh` | nie |
| `run_all.sh` | środowisko, walidacja, kampania (R) | nie |
| `run_benchmark.sh` | kampania: `strong11`, `node11`, `raw.jsonl`, `RESUME` | tak (kawałki, pomijanie po timeoucie) |
| `check_chain11.py` | bramki: typy 10 kolumn i przepływ 11 filtrów w każdym pliku | tak (`chain_cuts` w 1. linii) |
| `bench_spec.py` | łańcuchy, kolumny, okresy i cięcia, `chain_cuts()` | tak (x/y) |
| `bench_common.py` | argumenty, fazy czasu, RSS, rekord `BENCH`, liczby zdarzeń | tak (`chain_cuts`, `file_entries`) |
| `bench_chain.py` | jeden pomiar łańcucha (J1, R, RDF w J3) | nie |
| `bench_pool.py` | pule `uproot-pool` / `python-pool` na całym węźle | tak (kawałki) |
| `impl_rdf.py` | łańcuch w RDataFrame | tak (cięcia ze `track_cuts`) |
| `impl_uproot.py` | łańcuch w uproot/awkward | tak (zakres wpisów) |
| `impl_python.py` | łańcuch w Pythonie (AsNumpy) | nie |
| `validate.py` | zgodność implementacji przed każdym krokiem Run 3 | nie |
| `bench_filter.py`, `bench_efficiency.py` | wołane przez `validate.py` | nie |
| `dataset_json.py` | `dataset.json` w katalogu wyników | nie |
| `plot_results.py` | `bench.csv`, wykresy, tabele | nie |
| `plot_real_vs_synthetic.py` | analiza: rysunek pełnych plików, tabela zbiorów | nie |
| `plot_memory_control.py` | analiza: Block M | nie |
| `environment.yml` | env `pps-bench` | nie |
| `README.md`, `FINAL.md` | opis | tak |
| `app/analyze_proton_events.py`, `app/apply_corrections.py`, `app/diamond_geometry.py`, `app/efficiency.json` | kod analizy, z którego biorą implementacje i `validate.py` | nie |
| `corrections-examples/build_correction.py` | JSON correctionlib z `app/efficiency.json` dla `bench_efficiency.py` w `validate.py` | nie |
| `examples/test.root` | próbka do `validate.py` (Git LFS) | nie |

Przeniesione do `archive/` w tej rundzie: `make_bigset.sh` (kopie sztucznego zbioru),
`make_slim.py` (zbiór slim; `run_benchmark.sh` woła go stamtąd dla T6), `run3_helios.sh`
(osobne zadania Run 3 na `plgrid`).
