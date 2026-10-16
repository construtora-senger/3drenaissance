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
| `src/hall.js` | Cena do hall: aplica os lightmaps e a captura de reflexos, recria as luzes dos móveis e abre as portas |
| `src/walk-controls.js` | Caminhada no hall (teclado, arrastar para olhar, joystick no celular) e colisões |
| `src/assets.js` | Download, descompressão e leitura dos modelos 3D |
| `assets/model.json` | Dados dos modelos: tamanhos, enquadramento, mapa de caminhada, luzes e pontos de vista do hall |
| `assets/model-01…05.bin` | Prédio (glTF comprimido com gzip, dividido em partes) |
| `assets/hall-model-01…02.bin` | Hall de entrada (baixado só quando o visitante entra) |
| `assets/hall-lightmap*.jpg`, `assets/hall-env.hdr` | Iluminação calculada do hall e captura de reflexos |
| `assets/*-mobile-textures.json` | Texturas leves usadas em celulares e tablets |
| `assets/render-*.jpg` | Renders de referência mostrados em "Comparar com os renders" |
| `tools/hall/` | Fluxo de produção do hall (Blender e empacotamento), ver abaixo |

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

## Hall de entrada (fluxo de produção)

O hall é reconstruído a partir dos desenhos, não do SketchUp:

- **Arquitetura:** pranchas A02 (térreo), A03 (pav. 02), A14 e A15 (cortes). Pé-direito duplo de 5,78 m, mezanino do pav. 02 a 3,24 m com guarda-corpo de 1,10 m, fachada facetada com vidro até 5,78 m e hall dos elevadores com forro a 2,74 m.
- **Acabamentos e decoração:** render de referência (nogueira, forro ripado, latão, couro, bouclê). Onde o memorial é explícito, ele vale: caixilhos em alumínio anodizado branco, rodapé de granito de 10 cm e forro de gesso no corredor dos elevadores.

Etapas, todas reproduzíveis:

| Comando | O que faz |
| --- | --- |
| `npm run hall:textures` | Gera as texturas contínuas (nogueira, porcelanato 120×120, textura mineral, granito, metais) em `build/hall/textures` |
| `node tools/hall/decode_glb.mjs …` | Prepara o modelo antigo do hall (de onde vêm os móveis) para o Blender. O comando completo está no início do arquivo |
| `bpyenv/bin/python tools/hall/build_hall.py -- build/hall/hall-plain.glb build/hall/hall.blend` | Monta a cena no Blender: arquitetura paramétrica pelas cotas, decoração, luzes do render e móveis reaproveitados do modelo anterior |
| `bpyenv/bin/python tools/hall/preview.py -- build/hall/hall.blend <pasta>` | Prévias em Cycles dos principais pontos de vista |
| `bpyenv/bin/python tools/hall/bake_export.py -- build/hall/hall.blend build/hall/out 256 4096` | Calcula a iluminação (lightmaps), a captura de reflexos e a grade de caminhada, e exporta o glTF |
| `npm run hall:package` | Comprime e divide o modelo, gera as versões leves para celular e atualiza `assets/model.json` |

`bpyenv` é um ambiente Python 3.11 com o Blender como módulo (`pip install bpy==4.5.4`, mais `pillow`).

No site, `src/hall.js` aplica os lightmaps (segundo UV de cada malha) e a captura de reflexos. Paredes, piso e forro não usam luz em tempo real. Só os móveis e os metais, que não têm lightmap, recebem as luzes do Blender recriadas em tempo real (menos luzes no celular).

## Publicação

O GitHub Pages publica a partir do branch `main`. Depois que as mudanças entram no `main`, o site atualiza em alguns minutos. O arquivo `.nojekyll` precisa continuar na raiz.
