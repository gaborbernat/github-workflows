`build-maturin-wheels` passes `--interpreter` only for matrix entries that set `python`, so cross targets build again,
and it no longer enables sccache on Windows, where it broke MSVC builds of C dependencies.
