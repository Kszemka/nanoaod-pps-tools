# Wyniki

Każdy katalog z wynikami ma `raw.jsonl` (rekord na bieg), `bench.csv` i wykresy z
`test/plot_results.py`. Wszystkie wejścia są czytane z dysku po wyrzuceniu z page cache.

Na Heliosie wszędzie biegnie łańcuch 11 filtrów (10 gałęzi, `bench_chain.py --chain long`,
test `chain11`), na jednym zbiorze ~1 TB na raz. Pełne pliki to ~1 TB na dysku, z którego pętla
czyta kilka procent; slim to 1,5 TB czytane w całości.

| katalog | maszyna | dane | łańcuch | biegi | w pracy | stan |
|---|---|---|---|---|---|---|
| `single-core-ares/` | Ares, 1 rdzeń (`taskset`) | 1–9 kopii `ds_x32` (11,1–99,9 mln zdarzeń), pełne pliki, ZSTD:5 | 5 filtrów, filtr, efektywność | seria rozmiarów RDF / uproot / Python, struktura zapytania na 9 kopiach | `bench_input_size`, `bench_implementations_100m`, tabela query structure | jest |
| `synthetic-slim/` | Helios | 96 plików slim (10 gałęzi), 29,8 mld zdarzeń, 1,54 TB | 11 filtrów | T1 1–192 (96–192: 2–4 biegi), T2 1–96 | `bench_speedup_slim`, `bench_scalability_slim.tex`, `bench_weak_slim`; wiersz slim w tabeli zbiorów | jest |
| `full-chain11/artificial-1tb/` | Helios | 96 kopii `ds_x32`, pełne pliki (1984 gałęzie), 1,07 mld zdarzeń, 1,04 TB | 11 filtrów | T1 1–192, 96–192 trzy razy | tylko test pamięci (blok M, para ze slim: te same zdarzenia, 1984 wobec 10 gałęzi), `bench_memory_control`; nie wchodzi do rysunku i tabeli pełnych plików, bo 5 mln koszyków na plik (10–30× więcej niż dane rzeczywiste) zawyża koszt wątku | jest |
| `full-chain11/run2-1tb/` | Helios | Run 2 Open Data (Run2016H, G), 653 pliki, 1,05 mld zdarzeń, 1,04 TB, LZMA:9 | 11 filtrów, `--period 2016` (cięcia z 2A2D52E2, przepuszcza 1,9%) | jak wyżej | rysunek pełnych plików, tabela zbiorów; czas pętli to najszybszy z trzech biegów (`--best-of`), bo powtórki od 112 wątków zakłócało równoległe pobieranie Run 3 na ten sam Lustre | jest (brak `run2_chain11_gate.txt`) |
| `run3/chain11/` | Helios | Run 3 `core.txt`: 2307 plików z er Run2024C–Run2026D, 1,29 mld zdarzeń, 1,77 TB, LZMA:9 | 11 filtrów, cięcia Run 3 (`PERIODS["run3"]`, `test/README.md`, „Cięcia Run 3”) | J1: T1 1–192, 80–192 trzy razy | rysunek pełnych plików, tabela zbiorów | czeka na krok J1 |
| `run3/node/` | Helios | Run 3 `core.txt`, cały zbiór | 11 filtrów, cięcia Run 3 | J3: RDF na 192 wątkach i `uproot-pool` na 192 procesach, po 3 biegi | `17_whole_node.png` (sekcja Whole Node) | czeka na krok J3 |
| `comparison/` | — | z katalogów powyżej | — | — | `full_files_chain11.png`, `sets_summary.{csv,tex}` (Run 2, Run 3, slim); `memory_control.{png,csv}` (sztuczne pełne vs slim) | jest; Run 3 tymczasowo z `archive/run3-cuts2026/chain11`, do zastąpienia przez `run3/chain11/` po J1 |
| `archive/` | — | kampanie, które nie idą do pracy | — | — | — | — |

`archive/`:

| katalog | co to jest | dlaczego poza pracą |
|---|---|---|
| `chain5/helios-full/` | pełne kopie `ds_x32`, 11 M / 100 M / 355 M / 1 TB, filtr, łańcuch 5 filtrów, efektywność, T1 do 192 (`full-1tb` = scalone `full-1tb-job1` i `-job2`) | łańcuch 5 filtrów; zastępuje go `full-chain11/artificial-1tb` |
| `chain5/run2-opendata/` | Open Data 89 M / 356 M / 1 TB, łańcuch 5 filtrów `--period 2016` | jak wyżej; zastępuje go `full-chain11/run2-1tb` |
| `chain5/control-1tb/` | punkty kontrolne na kopiach `ds_x32` obok Open Data | jak wyżej |
| `chain5/memtest/` | 384 × `ds_x32_head.root` (1/10 koszyków), z page cache | test układu pliku (koszyki vs gałęzie) |
| `chain5/layout/` | `14_optimum_vs_size.png`, `16_memory_layout.png`, `summary_memory_layout.csv` | rysunki z łańcucha 5 filtrów; z `16_*`: koszt wątku rośnie z koszykami na plik (`ds_x32` ~5 mln, Open Data ~0,5 mln) |
| `run3-cuts2026/` | J1 (`chain11/`: r1 1–192 wątki, r2 32–192 na drugim węźle) i J2 (`chain11-weak/`) na Run 3 z cięciami 2026, czyli z próbki `examples/test.root` (RP 22, pary 23\|123 i 3\|103) | cięcia nie pasują do er 2024F–2026D: przepuszczają 10,8%, w kilku erach prawie nic, a praca dalszych filtrów zależy od tego, ile zdarzeń do nich dochodzi; zastępują je pomiary z cięciami Run 3. Zostaje jako kontrola: te same pliki przy innej selekcji pokazują, czy selektywność zmienia kształt skalowania |
| `run2-nopass/` | pierwszy krok R na Run 2 Open Data, cięcia 2016 sprzed poprawki, z cięciami torów z 2026 (`single_rp_idx == -1`, `time != 0`, `time_unc != 0`), których tory paskowe nie spełniają | łańcuch nie przepuścił żadnego zdarzenia, więc mierzył tylko filtry do pierwszego pustego; zastąpiony przez `full-chain11/run2-1tb` |
| `slim11-r5r6/` | zbiór slim jak `synthetic-slim/` plus trzecia dogrywka r5, r6 | sesja r5/r6 była w całości zakłócona przez Lustre (112 wątków: 1082 i 965 s wobec 416 s), pominięta |
| `ares-10gb-cached/` | dawna kampania 10 GB z page cache | nieużywana w pracy |

Zabranie wyników ostatecznej kampanii (`test/slurm_final.sbatch`) z Heliosa, bo scratch jest
czyszczony:

```bash
rsync -a helios:'$SCRATCH/bench/results-helios-run2-chain11-1tb/' results/full-chain11/run2-1tb/
rsync -a helios:'$SCRATCH/bench/results-helios-run3-chain11/'     results/run3/chain11/
rsync -a helios:'$SCRATCH/bench/results-helios-run3-node/'        results/run3/node/
scp helios:'$SCRATCH/bench/run2_chain11_gate.txt' results/full-chain11/run2-1tb/
scp helios:'$SCRATCH/bench/run3_chain11_gate.txt' results/run3/chain11/
scp helios:'$SCRATCH/bench/final_progress.log'    results/run3/
python test/plot_results.py --results results/run3/node
```

Rysunki i tabele porównania:

```bash
python test/plot_real_vs_synthetic.py --out results/comparison \
    --set "results/full-chain11/run2-1tb:chain11:Run 2 Open Data" \
    --set "results/run3/chain11:chain11:Run 3" \
    --set "results/synthetic-slim:chain11:artificial, slim files" \
    --figure "Run 2 Open Data" --figure "Run 3" \
    --best-of "Run 2 Open Data"

python test/plot_memory_control.py --out results/comparison \
    --set "results/full-chain11/artificial-1tb:chain11:artificial, full files" \
    --set "results/synthetic-slim:chain11:artificial, slim files" \
    --profile "artificial, full files" --files "artificial, full files:96"
```

Zbiory, których katalogu jeszcze nie ma, skrypt pomija z ostrzeżeniem. `--best-of` bierze dla
danego zbioru najszybszy bieg w każdym punkcie zamiast mediany i oznacza go `*` w tabeli.

`plot_memory_control.py` rysuje szczyt RSS, RSS z końca pętli (maksimum z ostatnich 10% fazy
`loop` w `rss_*.csv`) i RSS w czasie pętli. `--files LABEL:N` dopasowuje RSS z końca pętli do
`max(T, min(2T, N))` otwartych drzew: na kopiach 157 MB na drzewo, rms 0,2 GB (prosta w T:
1,9 GB). Slim ma tylko szczyt, bo sampler tamtej kampanii nie zbierał próbek w czasie pętli.

Do czasu J1 obecne `comparison/` jest zrobione z Run 3 z cięciami zbioru sztucznego
(`PERIODS["2026"]`, czyli z `examples/test.root`; „2026” to nazwa zestawu cięć, nie lat danych,
które obejmują 2024–2026), zamiast drugiego `--set`:

```bash
    --set "results/archive/run3-cuts2026/chain11:chain11:Run 3, cuts of the artificial files" \
    --figure "Run 3, cuts of the artificial files"
```

Do pracy (rysunki `fig:bench_full_files`, `fig:bench_memory_control`, `fig:bench_whole_node` i tabela `tab:sets_summary` wczytują te pliki same,
gdy istnieją; do tego czasu w PDF stoi `[pending: ...]`):

```bash
cp results/comparison/full_files_chain11.png doc/Images/bench_full_files.png
cp results/comparison/sets_summary.tex doc/Tables/sets_summary.tex
cp results/comparison/memory_control.png doc/Images/bench_memory_control.png
cp results/run3/node/17_whole_node.png doc/Images/bench_whole_node.png
```

Miejsca w tekście, które czekają jeszcze na J1 (cięcia Run 3) i J3 (cały węzeł):
`grep -rn '\\pending' doc/Chapters`. Po J1 trzeba też usunąć z podpisów i tekstu
„Run~3 with the cuts of the artificial files”.
