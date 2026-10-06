<p align="center"><img src="docs/images/gameremote.png" width="160" alt="GameRemote logo"></p>

# GameRemote

GameRemote is a local development project for PlayStation 4 and PlayStation 5
Remote Play. It combines a shared C protocol core with a Qt desktop client,
a Kotlin Android client and an in-progress native Swift iPhone/iPad client.

Start with the [release and validation guide](docs/release/README.md) for platform
build instructions, verified results and remaining requirements. The
[design handoff](docs/design/README.md) records the interface specification and
its evidence boundaries. [Packaging notes](scripts/PACKAGING.md) identify the
current GameRemote entry points and retained upstream tools.

These sources and local validation records do not establish that every platform
has a working, signed or published release. No GameRemote store listing or
public download service is configured here.

## Licence and provenance

GameRemote is a derivative of [chiaki-ng](https://github.com/streetpea/chiaki-ng),
which builds on the original [Chiaki](https://git.sr.ht/~thestr4ng3r/chiaki)
project. The source is licensed under [AGPL-3.0-only](COPYING), with the existing
[OpenSSL additional permission](LICENSES/AGPL-3.0-only-OpenSSL.txt).
Preserve upstream author, copyright, licence and third-party notices; see the
[existing legal notice](docs/prototype/NOTICE.md) and
[documentation provenance](docs/upstream-documentation.md).

This project is not endorsed or certified by Sony Interactive Entertainment LLC.
