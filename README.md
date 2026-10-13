<div align="center">

<img src="logo.png" alt="Handwave" width="220">

# Handwave

**Controle e efeitos visuais em tempo real a partir do movimento das suas mãos.**

Uma aplicação desktop em Python que conecta a câmera automaticamente, rastreia as mãos com visão computacional e desenha tudo dentro de uma interface de vidro inspirada no macOS.

<br>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/PySide6-Qt_6-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-Hand_Landmarker-0097A7?style=for-the-badge&logo=google&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)

![Windows](https://img.shields.io/badge/Windows-11-0078D4?style=flat-square&logo=windows11&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-compatível-000000?style=flat-square&logo=apple&logoColor=white)
![Status](https://img.shields.io/badge/status-em_desenvolvimento-4078FF?style=flat-square)

</div>

---

## Sumário

- [Visão geral](#visão-geral)
- [Recursos](#recursos)
- [Como funciona](#como-funciona)
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Uso](#uso)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Design](#design)
- [Roadmap e ideias](#roadmap-e-ideias)

---

## Visão geral

O Handwave transforma a webcam em uma superfície de interação. Assim que o app abre, ele procura uma câmera disponível, inicia o rastreamento e desenha o esqueleto de cada mão por cima do vídeo, com 21 pontos por mão. Isso serve de base para efeitos visuais e, mais à frente, para controle por gestos.

| | Destaque | Detalhe |
|:-:|---|---|
| <img src="https://api.iconify.design/lucide/camera.svg?color=%234078ff" width="22"> | Câmera automática | Testa os dispositivos disponíveis e reconecta sozinho se a câmera cair |
| <img src="https://api.iconify.design/lucide/hand.svg?color=%234078ff" width="22"> | Rastreamento de mãos | Até duas mãos ao mesmo tempo, com filtro One Euro contra tremidas |
| <img src="https://api.iconify.design/lucide/layers.svg?color=%234078ff" width="22"> | Interface de vidro | Desfoque acrylic nativo do Windows, cantos arredondados e brilho azul |
| <img src="https://api.iconify.design/lucide/gauge.svg?color=%234078ff" width="22"> | Tempo real | Captura e inferência rodam fora da thread da interface, até 30 fps |

---

## Recursos

- **Conexão automática** com a primeira câmera que responder, sem configuração
- **Reconexão** quando a câmera é desconectada ou para de enviar quadros
- **Rastreamento de 21 pontos** por mão usando o MediaPipe Hand Landmarker
- **Pontos estáveis** mesmo com a mão inclinada, graças à imagem quadrada enviada ao modelo
- **Esqueleto com brilho** desenhado em vetor, nítido em qualquer resolução
- **Controles na barra lateral** para mostrar as mãos, espelhar, trocar de câmera, pausar e salvar foto
- **Janela sem moldura** com arrastar, redimensionar pelas bordas e maximizar
- **Download automático do modelo** na primeira execução

---

## Como funciona

### Fluxo principal

```mermaid
flowchart LR
    A([Início]) --> B[Abrir janela]
    B --> C[Iniciar CameraWorker]
    C --> D{Modelo existe?}
    D -- Não --> E[Baixar hand_landmarker.task]
    E --> F[Carregar HandTracker]
    D -- Sim --> F
    F --> G{Câmera encontrada?}
    G -- Não --> H[Aguardar 1,5 s]
    H --> G
    G -- Sim --> I[Loop de captura]
    I --> J{Quadro válido?}
    J -- Sim --> K[Processar e enviar à UI]
    K --> I
    J -- Falhas seguidas --> G
```

### Pipeline de cada quadro

```mermaid
flowchart LR
    A[Quadro BGR<br/>1280 x 720] --> B[Espelhar]
    B --> C[Converter para RGB]
    C --> D[MediaPipe<br/>Hand Landmarker]
    D --> E[21 pontos<br/>por mão]
    E --> F[Suavização<br/>exponencial]
    F --> G[Sinal Qt<br/>frame_ready]
    G --> H[CameraView<br/>desenha vídeo + mãos]
```

### Comunicação entre threads

```mermaid
sequenceDiagram
    participant UI as MainWindow (thread da UI)
    participant W as CameraWorker (QThread)
    participant T as HandTracker
    participant C as Câmera

    UI->>W: start()
    W->>T: carregar modelo
    W->>C: abrir dispositivo
    W-->>UI: status_changed("live")
    loop a cada quadro
        C->>W: quadro
        W->>T: process(rgb, timestamp)
        T-->>W: lista de Hand
        W-->>UI: frame_ready(imagem, mãos, fps)
        UI->>UI: repintar CameraView
    end
    UI->>W: requestInterruption()
    W->>T: close()
```

---

## Arquitetura

```mermaid
flowchart TB
    main[main.py<br/>ponto de entrada] --> window[window.py<br/>MainWindow]
    window --> widgets[widgets.py<br/>CameraView, SideButton, TitleBar]
    window --> blur[blur.py<br/>acrylic e recorte da janela]
    window --> camera[camera.py<br/>CameraWorker]
    camera --> tracker[tracker.py<br/>HandTracker]
    widgets --> gestures[gestures.py<br/>GestureReader]
    widgets --> effects[effects/<br/>efeitos registrados]
    effects --> gestures
    gestures --> tracker
    tracker --> model[(hand_landmarker.task)]
```

| Módulo | Responsabilidade |
|---|---|
| `main.py` | Cria a aplicação Qt, define fonte, ícone e abre a janela |
| `window.py` | Janela principal, ações da barra lateral, redimensionamento e ciclo de vida da câmera |
| `widgets.py` | Componentes visuais: vídeo com esqueleto das mãos, botões e barra de título |
| `camera.py` | Thread que encontra a câmera, captura quadros e chama o rastreador |
| `tracker.py` | Envolve o MediaPipe, baixa o modelo e suaviza os pontos |
| `gestures.py` | Interpreta cada mão: dedo apontando, gesto de L, velocidade da ponta do indicador |
| `effects/` | Um arquivo por efeito, todos seguindo o mesmo contrato |
| `blur.py` | Chamadas nativas do Windows para o desfoque e os cantos arredondados |

---

## Efeitos

Cada efeito mora em um arquivo próprio dentro de `effects/` e segue o contrato de `effects/base.py`. A barra lateral monta os botões sozinha a partir da lista em `effects/__init__.py`, e só um efeito fica ativo por vez.

```mermaid
flowchart LR
    A[Quadro da câmera] --> B[HandTracker<br/>21 pontos por mão]
    B --> C[GestureReader<br/>pose, gestos e velocidade]
    C -->|set_hands a cada quadro| D[Efeito ativo]
    E[Relógio de 60 fps] -->|tick| D
    D -->|draw| F[CameraView]
```

| Método | Quando é chamado | Para que serve |
|---|---|---|
| `set_hands(poses)` | A cada quadro novo da câmera | Ler as mãos e decidir o que o efeito faz |
| `tick(dt)` | 60 vezes por segundo | Animar, mesmo entre quadros da câmera |
| `draw(painter)` | A cada repintura | Desenhar por cima do vídeo, em pixels do quadro |
| `set_frame(imagem)` | A cada quadro, só se `wants_frame` for verdadeiro | Receber os pixels da câmera para filtrar |
| `dim` | Antes de desenhar | De 0 a 1, quanto o vídeo escurece por baixo do efeito |
| `idle` | A cada tick | Quando verdadeiro, a tela para de repintar a 60 fps |
| `close()` | Ao desligar o efeito | Liberar threads e recursos |

### Desempenho

- O quadro da câmera é redimensionado uma vez por quadro novo, não a cada repintura
- Os brilhos das partículas usam sprites prontos em cada tamanho, sem redimensionar na hora
- Os números são textos pré-calculados e as linhas da rede são desenhadas em lotes
- Sem efeito aceso, a animação não repinta a tela

### Bola de energia

<img src="https://api.iconify.design/lucide/orbit.svg?color=%234078ff" width="20"> Um orbe de luz com partículas e números em estilo ASCII, inspirado em efeitos feitos no TouchDesigner. Cada partícula tem uma órbita própria em 3D: fechada, a bola é uma esfera; aberta, vira um disco inclinado em que as partículas de dentro giram mais rápido, e as mais próximas da câmera brilham mais.

```mermaid
stateDiagram-v2
    [*] --> NoDedo: indicador apontando
    NoDedo --> Voando: peteleco na direção da outra mão
    Voando --> NoDedo: chega ao indicador da outra mão
    NoDedo --> Expandida: L com a outra mão
    Expandida --> NoDedo: desfaz o L
    NoDedo --> [*]: mão fechada ou fora da câmera
```

| Gesto | Resultado |
|---|---|
| Apontar com o indicador | A bola acende com uma explosão de faíscas e acompanha a ponta do dedo |
| Fechar a mão que segura a bola | Depois de um instante a bola se apaga; apontar de novo acende outra vez |
| Peteleco rápido na direção da outra mão | A bola voa em arco até o outro indicador, deixando rastro |
| L com a outra mão | A bola se abre num disco de partículas em perspectiva, centrado no dedo que a segura, com as partículas numeradas ligadas em rede; quanto mais longe a mão do L, maior o disco |
| Girar a mão do L | O disco gira junto, como um botão giratório |
| Mover a mão que segura | O disco acompanha o dedo |
| Desfazer o L | O disco se recolhe de volta para a bola |

### Prisma

<img src="https://api.iconify.design/lucide/box.svg?color=%234078ff" width="20"> Uma caixa 3D presa entre as duas mãos abertas, em que cada face funciona como uma lente com um filtro diferente sobre o vídeo.

```mermaid
flowchart LR
    A[Quadro da câmera] --> B[Thread de filtros]
    B --> C[Térmico]
    B --> D[Pontos azuis]
    B --> E[Lápis]
    C --> F[Face da frente]
    D --> G[Topo e fundo]
    E --> H[Laterais]
    F & G & H --> I[Caixa entre as mãos]
```

| Gesto | Resultado |
|---|---|
| Abrir as duas mãos com indicador e polegar afastados | A caixa aparece com a frente indo do indicador ao polegar de cada mão |
| Mover, aproximar ou afastar as mãos | A caixa estica, encolhe e acompanha, sempre se estendendo para o centro da tela |
| Fechar as mãos | A caixa desaparece |

Os filtros rodam numa thread separada, em 640x360, e custam menos de 1 ms na thread da interface.

### Tolerância a movimentos bruscos

Com a mão em movimento rápido, o borrão engana a leitura dos gestos. Por isso:

- Enquanto a ponta do indicador passa de 900 px/s, o gesto lido fica congelado no último valor
- Os efeitos toleram o gesto falhar por alguns décimos de segundo: a bola continua aberta e o prisma continua preso às mesmas mãos

### Criando um efeito novo

1. Crie `effects/meu_efeito.py` com uma classe que herda de `Effect`, definindo `name` e `icon`
2. Implemente `set_hands`, `tick` e `draw`
3. Adicione a classe na lista `EFFECTS` em `effects/__init__.py`

Com `python dev.py` rodando, o app recarrega a cada arquivo salvo.

---

## Instalação

**Requisitos:** Python 3.10 ou superior e uma webcam.

### Jeito rápido

Os inicializadores criam o ambiente virtual, instalam as dependências e abrem o app. Na primeira vez demoram alguns minutos; depois abrem direto.

| Sistema | Como abrir |
|---|---|
| <img src="https://api.iconify.design/simple-icons/windows.svg?color=%234078ff" width="18"> Windows | Duplo clique em `iniciar_windows.bat` |
| <img src="https://api.iconify.design/simple-icons/apple.svg?color=%234078ff" width="18"> macOS | Duplo clique em `iniciar_mac.command` |

No macOS, se o sistema bloquear o arquivo na primeira vez, clique com o botão direito e escolha Abrir. Se aparecer erro de permissão, rode `chmod +x iniciar_mac.command` no Terminal. O Terminal também vai pedir acesso à câmera.

```mermaid
flowchart LR
    A[Duplo clique] --> B{Python 3.10+?}
    B -- Não --> C[Mostra onde baixar]
    B -- Sim --> D{.venv existe?}
    D -- Não --> E[Cria o ambiente virtual]
    D -- Sim --> F[Confere as dependências]
    E --> F
    F --> G[Abre o Handwave]
```

### Jeito manual

```bash
git clone https://github.com/<seu-usuario>/Handwave.git
cd Handwave

python -m venv .venv
```

Ative o ambiente virtual:

```bash
# Windows
.venv\Scripts\activate

# macOS e Linux
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

---

## Uso

```bash
python main.py
```

Na primeira execução o modelo de mãos (cerca de 7 MB) é baixado para a raiz do projeto. Depois disso o app abre direto.

### Modo de desenvolvimento

```bash
python dev.py
```

Mantém o app aberto e reinicia automaticamente sempre que um arquivo `.py` do projeto é salvo.

```mermaid
flowchart LR
    A[dev.py] --> B[Abre o Handwave]
    B --> C{Arquivo .py salvo?}
    C -- Sim --> D[Encerra o app]
    D --> B
    C -- Não --> C
```

| Ação | Como fazer |
|---|---|
| Mover a janela | Arraste pela faixa superior |
| Redimensionar | Arraste qualquer borda |
| Maximizar | Botão no canto superior direito ou duplo clique na faixa superior |
| Tela cheia | Tecla F, só com a câmera na tela; Esc para sair |

### Atalhos

| Tecla | Ação |
|:-:|---|
| `H` | Mostrar ou ocultar o traçado das mãos |
| `M` | Espelhar a imagem |
| `1` | Ligar ou desligar a Bola de energia |
| `2` | Ligar ou desligar o Prisma |
| `C` | Trocar de câmera |
| `Espaço` | Pausar ou continuar |
| `S` | Salvar foto |
| `F` | Tela cheia |
| `Esc` | Sair da tela cheia |

### Barra lateral

| | Botão | Função |
|:-:|---|---|
| <img src="https://api.iconify.design/lucide/hand.svg?color=%234078ff" width="20"> | Mãos | Mostra ou oculta o traçado das mãos; o rastreamento continua ativo |
| <img src="https://api.iconify.design/lucide/flip-horizontal.svg?color=%234078ff" width="20"> | Espelhar | Inverte a imagem horizontalmente |
| <img src="https://api.iconify.design/lucide/orbit.svg?color=%234078ff" width="20"> | Bola de energia | Liga ou desliga o efeito; só um efeito fica ativo por vez |
| <img src="https://api.iconify.design/lucide/switch-camera.svg?color=%234078ff" width="20"> | Trocar câmera | Passa para a próxima câmera conectada |
| <img src="https://api.iconify.design/lucide/pause.svg?color=%234078ff" width="20"> | Pausar | Congela a imagem até clicar de novo |
| <img src="https://api.iconify.design/lucide/camera.svg?color=%234078ff" width="20"> | Foto | Salva o quadro com as mãos desenhadas em Imagens/Handwave |

---

## Estrutura do projeto

```
Handwave/
├── main.py              Ponto de entrada
├── dev.py               Recarregamento automático
├── window.py            Janela principal
├── widgets.py           Componentes visuais
├── camera.py            Captura em thread separada
├── tracker.py           Rastreamento de mãos
├── gestures.py          Leitura de gestos
├── effects/
│   ├── __init__.py      Registro dos efeitos
│   ├── base.py          Contrato de um efeito
│   ├── render.py        Brilho e fonte compartilhados
│   ├── energy_ball.py   Bola de energia
│   └── prism.py         Prisma
├── iniciar_windows.bat  Prepara e abre o app no Windows
├── iniciar_mac.command  Prepara e abre o app no macOS
├── blur.py              Efeito de vidro no Windows
├── logo.png             Identidade visual
└── requirements.txt     Dependências
```

---

## Design

A interface segue a linguagem de vidro do macOS, adaptada a um tema escuro e azulado.

| Elemento | Escolha |
|---|---|
| Fundo da janela | Acrylic nativo com tinta azul translúcida e borda clara de 1 px |
| Cantos | Raio de 26 px na janela e 20 px na área da câmera |
| Cor de destaque | `#4078FF` |
| Botões laterais | Círculos de vidro centralizados na vertical; quando ligados, ficam preenchidos em azul e com brilho |
| Logo | Só a mão do logo, recortada automaticamente, ao lado do nome no topo da janela |
| Mãos | Linhas finas azul claro com halo, pontos brancos e pontas dos dedos maiores |
| Tipografia | SF Pro no macOS e Segoe UI Variable no Windows |

---

## Roadmap e ideias

```mermaid
flowchart LR
    subgraph F1[Fase 1: Base]
        A1[Câmera automática]
        A2[Rastreamento de mãos]
        A3[Interface de vidro]
    end
    subgraph F2[Fase 2: Efeitos]
        B1[Bola de energia]
        B2[Ondas]
        B3[Foco]
        B4[Fogo]
        B5[Gelo]
    end
    subgraph F3[Fase 3: Interação]
        C1[Reconhecimento de gestos]
        C2[Atalhos do sistema]
        C3[Gravação e captura]
    end
    F1 --> F2 --> F3
```

- [x] Conexão automática com a câmera
- [x] Rastreamento de até duas mãos
- [x] Interface de vidro com controles na barra lateral
- [x] Mostrar mãos, espelhar, trocar câmera, pausar e salvar foto
- [x] **Bola de energia:** orbe no indicador, passagem entre as mãos por peteleco e expansão com o gesto de L
- [ ] **Ondas:** rastros suaves que seguem as pontas dos dedos
- [ ] **Foco:** um anel que acompanha a pinça entre polegar e indicador
- [ ] **Fogo:** chamas saindo das pontas dos dedos, com intensidade pela velocidade da mão
- [ ] **Gelo:** cristais que crescem a partir da palma aberta
- [ ] Reconhecimento de gestos: pinça, punho fechado, mão aberta e apontar
- [ ] Controle do sistema por gestos, como volume, mídia e troca de janelas
- [ ] Tela de configurações: câmera, sensibilidade e número de mãos
- [ ] Captura de tela e gravação de vídeo com os efeitos aplicados
- [ ] Blur nativo no macOS com `NSVisualEffectView`

---

<div align="center">

Feito com Python, Qt e MediaPipe.

</div>
