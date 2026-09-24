# Prepared Python dependency

The node installer uses the declared, SHA-256 verified ANTLR runtime wheel in
this directory. OmegaConf needs ANTLR 4.9; PyPI's 4.9.3 release only supplies a
source archive. End users do not need a compiler or a Python packaging toolchain.

This author build changes no runtime Python file. It omits the unused `pygrun`
command, includes the upstream BSD licence, and identifies the packaging change
with the local version `4.9.3+lds.1`. See `provenance.json` for the source and
wheel hashes. Two independent Windows builds produced the same wheel bytes.

To reproduce as a plugin author on Python 3.12, install `setuptools==78.1.0` and
`wheel==0.46.1` in a disposable build environment, then run
`python authoring/build_antlr.py --output <empty-output-directory>` from
this plugin. The script checks the source and bundled licence before building,
then refuses a different wheel hash. The `authoring/` directory stays in the
plugin's source repository and is excluded from installable packages.

The bundled wheel is a preparation dependency only. Successful dependency
installation is not a successful GPU render: LDS checks the actual ComfyUI
classes and model files separately before reporting SeedVR2 ready.
