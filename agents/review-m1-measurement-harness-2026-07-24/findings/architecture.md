# Architecture review findings
- F3 MEDIUM: main.rs extract_fixture_features doc comment claims sharing with run_fixture that doesn't exist; ~24 linhas de lógica de reordenação [mel*n_frames] duplicadas (DRY). Fix antes do merge.
- F1/F2/F4 INFO, F5 LOW: DIP/layering intacto, pub(crate) correto, composition root ok, ThermalRatio unit struct (nit).
- Nenhum BLOCKER/HIGH.
