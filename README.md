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
| <img src="https://api.iconify.design/lucide/hand.svg?color=%234078ff" width="22"> | Rastreamento de mãos | Até duas mãos ao mesmo tempo, com suavização para reduzir tremidas |
| <img src="https://api.iconify.design/lucide/layers.svg?color=%234078ff" width="22"> | Interface de vidro | Desfoque acrylic nativo do Windows, cantos arredondados e brilho azul |
| <img src="https://api.iconify.design/lucide/gauge.svg?color=%234078ff" width="22"> | Tempo real | Captura e inferência rodam fora da thread da interface, a 30 fps |

---

## Recursos

- **Conexão automática** com a primeira câmera que responder, sem configuração
- **Reconexão** quando a câmera é desconectada ou para de enviar quadros
- **Rastreamento de 21 pontos** por mão usando o MediaPipe Hand Landmarker
- **Imagem espelhada**, para que o movimento na tela acompanhe o seu
- **Esqueleto com brilho** desenhado em vetor, nítido em qualquer resolução
- **Barra lateral de modos** pronta para receber os efeitos visuais
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
    widgets --> tracker
    tracker --> model[(hand_landmarker.task)]
```

| Módulo | Responsabilidade |
|---|---|
| `main.py` | Cria a aplicação Qt, define fonte, ícone e abre a janela |
| `window.py` | Janela principal, barra lateral de modos, redimensionamento e ciclo de vida da câmera |
| `widgets.py` | Componentes visuais: vídeo com esqueleto das mãos, botões e barra de título |
| `camera.py` | Thread que encontra a câmera, captura quadros e chama o rastreador |
| `tracker.py` | Envolve o MediaPipe, baixa o modelo e suaviza os pontos |
| `blur.py` | Chamadas nativas do Windows para o desfoque e os cantos arredondados |

---

## Instalação

**Requisitos:** Python 3.10 ou superior e uma webcam.

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
| Trocar de modo | Clique nos botões da barra lateral |

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
| Botões laterais | Círculos de vidro, com o modo ativo preenchido em azul e com brilho |
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
        B1[Energia entre as mãos]
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
- [x] Interface de vidro com barra lateral de modos
- [ ] **Energia:** partículas e um núcleo de luz que se formam entre as duas mãos e reagem à distância entre elas
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
