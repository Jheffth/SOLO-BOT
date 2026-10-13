# Componentes de terceiros

O pacote contém os binários oficiais de `vosk-win64-0.3.45` e o modelo
`vosk-model-small-pt-0.3`, distribuídos pela Alpha Cephei. Vosk e o modelo português
usam Apache License 2.0. Copyright 2020–2021 Alpha Cephei Inc. para a API.

Fontes e código da versão: https://github.com/alphacep/vosk-api/tree/v0.3.45
Modelo: https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip

Os binários oficiais incluem as bibliotecas de execução GCC `libstdc++-6.dll`,
`libgcc_s_seh-1.dll` e `libwinpthread-1.dll`. Consulte os termos correspondentes
do GCC/MinGW e a GCC Runtime Library Exception nos links abaixo. Os arquivos de
licença são incluídos na pasta `licencas` durante a compilação. O README original
do modelo também permanece em `modelo`.

- Apache 2.0: https://www.apache.org/licenses/LICENSE-2.0
- GCC runtime: https://www.gnu.org/licenses/gcc-exception-3.1.html
- GCC source: https://gcc.gnu.org/git.html
- MinGW-w64 source and licenses: https://www.mingw-w64.org/

Windows, WinForms, WinMM, System.Speech e DPAPI são componentes do Windows/.NET
Framework; não são redistribuídos neste pacote.
