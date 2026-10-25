# Assets nativos — etapas 2, 3 e 4

1. Prepare os recortes em assets/crops/{id}.png e inspecione as referências
   locais antes de editar. Recorte determinístico é preparação; geração e
   edição criativa usam a ferramenta nativa de imagem.
2. Separe assets independentes de dependentes. Respeite os limites da
   ferramenta; execução sequencial é válida. Não exija shell em segundo
   plano, comando wait ou agentes paralelos.
3. Use image_gen.imagegen, exposta em code mode como tools.image_gen__imagegen.
   Em edição com referências locais, use referenced_image_paths. Se alguma
   referência só existir na conversa, use num_last_images_to_include com o
   menor número necessário (até cinco). Nunca combine ambos. Para geração
   nova, omita ambos. Não invente parâmetros de modelo, resolução ou filename.
4. Use transparent_background=true para ícones e camadas recortadas, false
   para fundos completos. Preserve transparência em edições salvo instrução
   contrária. Descreva proporção, materiais, iluminação e enquadramento no
   prompt. Não imponha flat a fotos, 3D ou texturas.
5. Prompt exemplo: “Recrie o asset da referência, preservando geometria,
   materiais, cores e iluminação. Sem moldura ou padding extra. Apenas o
   asset com fundo transparente.” Para fundo: “Recrie somente a arte do
   fundo, sem textos, cards ou controles sobrepostos.”
6. Aguarde a conclusão real. Em code mode, use a diretiva inicial
   // @exec: {"yield_time_ms": 120000}
   e a mesma espera nos waits necessários, conforme o contrato de imagegen.
   Não imprima base64. Retorne a imagem por generatedImage(result).
7. A saída desta skill exige arquivos para o site: exporte pelos caminhos ou
   mecanismos realmente fornecidos pela ferramenta para assets/{id}.png.
   Não invente caminho nem integre URL temporária como mídia final. Se o
   resultado só fornecer prévia sem exportação acessível, explique o limite
   e mantenha a integração pendente. Não baixe/reenvie só para exibir/salvar
   uma geração; exporte apenas para a entrega HTML que necessita do asset.
8. Confira formato, dimensões, alpha e enquadramento do arquivo exportado,
   integre por caminho relativo e compare na composição. Refaça somente os
   assets falhos, preservando os aprovados. O gate pertence à etapa usuária.

Se imagegen não estiver disponível, informe. Não peça chave OpenRouter nem
troque silenciosamente de provedor. CSS/planejamento podem avançar dentro
do escopo aprovado; arte essencial ausente permanece pendente. Instalar esta
skill não solicita gerar imagens sem um mock de referência.
