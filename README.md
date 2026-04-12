# myco

> Rede silenciosa de consciência compartilhada entre sessões Claude.

**myco** é um daemon escrito em Rust que conecta múltiplas sessões do Claude Code trabalhando em projetos diferentes, permitindo que cada uma saiba em tempo real o que as outras estão fazendo — sem orquestrador central, sem broker, sem mediador humano.

A analogia é o micélio: uma rede subterrânea de fungos que conecta árvores aparentemente independentes, transportando sinais e nutrientes silenciosamente. Cada sessão Claude continua autônoma na sua "árvore" (seu próprio projeto, seu próprio contexto), mas as raízes compartilham um barramento que o `myco` mantém vivo e filtrado.

## O problema

Quando você coloca 3, 5 ou 10 sessões Claude pra trabalharem em projetos interdependentes — frontend, backend, microserviços, IAM — cada uma precisa saber o que as outras estão fazendo: quem está bloqueando quem, quais containers estão de pé, qual contrato de API está estável. Hoje, a única forma é o humano virar um mensageiro cansado, ou usar MCP (lento e pesado).

## A ideia em uma frase

> O filesystem num ramdisk já é um barramento de mensagens atômico, rápido e grátis. O `myco` só adiciona uma camada fina de curadoria inteligente em cima dele, com escrita atômica e leitura personalizada por sessão.

## Documentos

- [`docs/CONCEPT.md`](docs/CONCEPT.md) — a ideia completa, princípios e raciocínio
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — especificação do protocolo (logs, views, eventos)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — esboço do daemon em Rust
- [`examples/three-services/`](examples/three-services/) — exemplo real com SN + SM + IAM
- [`swarm/`](swarm/) — template do layout de runtime que o `myco` cria no ramdisk

## Status

Fase de design. Nada implementado ainda.

## Licença

MIT (a definir).
