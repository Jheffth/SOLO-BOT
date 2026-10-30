# Galeria da Bella

Coloque aqui as fotos e vídeos da Bella. O Solo Bot lê esta pasta (montada como `/app/dados/galeria`, somente leitura); não precisa reiniciar depois de subir arquivos.

    galeria/bella/bom_dia/    fotos do bom dia das 08:00 (carinhosas)
    galeria/bella/normal/     fotos e vídeos do dia a dia
    galeria/bella/sensual/    sensuais (só para o Arquiteto)
    galeria/bella/lingerie/   ┐
    galeria/bella/topless/    ├ NÃO são servidos até você incluí-los em BELLA_GALERIA_NIVEIS no .env
    galeria/bella/nu/         ┘

Formatos: jpg, png, webp e mp4 (até 15 MB). As mídias NÃO vão para o git (veja o .gitignore): suba-as direto na VPS
(`scp`/`rsync` para a pasta `galeria/` ao lado do `docker-compose.yml`).
Detalhes: seção "Galeria da Bella" em INTERACAO.md.
