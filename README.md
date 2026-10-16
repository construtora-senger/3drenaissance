# Renaissance Residence — visita virtual

Visita 3D do Renaissance Residence. O visitante gira o prédio, alterna entre vistas e entre dia e entardecer, e pode entrar no hall para caminhar em primeira pessoa. O site é estático e está publicado pelo GitHub Pages.

## Estrutura

| Caminho | O que é |
| --- | --- |
| `index.html` | Página: textos, botões e painéis |
| `styles.css` | Visual da página |
| `app.js` | Código do app já compilado (gerado por `npm run build`, não editar à mão) |
| `src/main.js` | Fluxo principal: carregamento, câmera, vistas, botões, entrada e saída do hall |
| `src/exterior.js` | Iluminação do prédio (dia e entardecer) e ajuste dos materiais |
| `src/hall.js` | Cena do hall: luzes, sombras de contato e a escultura dourada |
| `src/walk-controls.js` | Caminhada no hall (teclado, arrastar para olhar, joystick no celular) e colisões |
| `src/assets.js` | Download, descompressão e leitura dos modelos 3D |
| `assets/model.json` | Dados dos modelos: tamanhos, enquadramento e mapa de caminhada do hall |
| `assets/model-01…05.bin` | Prédio (glTF comprimido com gzip, dividido em partes) |
| `assets/hall-model-01.bin` | Hall de entrada (baixado só quando o visitante entra) |
| `assets/*-mobile-textures.json` | Texturas leves usadas em celulares e tablets |
| `assets/render-*.jpg` | Renders de referência mostrados em "Comparar com os renders" |

## Rodar localmente

Precisa do Node.js 20 ou mais recente.

```sh
npm install
npm run serve      # abre em http://localhost:8080
```

O site usa `fetch()`, então não funciona abrindo o `index.html` direto pelo arquivo. Use o servidor.

## Alterar o código

1. Edite os arquivos em `src/` (ou o `index.html` e o `styles.css`).
2. Rode `npm run build`. Isso gera o `app.js` e atualiza os códigos `?v=` do `index.html`, para os navegadores baixarem a versão nova.
3. Faça o commit do `app.js` junto com as alterações.

## Atualizar os modelos 3D

Os arquivos `.bin` são o `.glb` comprimido com gzip e cortado em partes de até ~8 MB. As partes ficam abaixo do limite de 25 MB do upload pelo site do GitHub. Ao trocar um modelo:

1. Comprima o `.glb` com gzip e divida em partes.
2. Atualize em `assets/model.json` os campos `bytes`, `parts` e `assetSHA256` (ou os de `hall`), e aumente o `version`.
3. Se o número de imagens do modelo mudar, gere de novo o `*-mobile-textures.json` correspondente, com uma imagem por textura do modelo e na mesma ordem.
4. Rode `npm run build`, porque o `model.json` é embutido no `app.js`.

## Publicação

O GitHub Pages publica a partir do branch `main`. Depois que as mudanças entram no `main`, o site atualiza em alguns minutos. O arquivo `.nojekyll` precisa continuar na raiz.
