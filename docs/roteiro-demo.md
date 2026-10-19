# Roteiro de demonstração — Conecta Já

Este roteiro executa os 12 passos de `docs/mvp.md` de ponta a ponta. Os comandos são para o PowerShell, a partir da raiz do repositório.

## Preparação

1. Suba o banco, o backend e o frontend (veja o `README.md`).
2. Crie os dados de exemplo com prazos curtos:

   ```powershell
   python backend\manage.py seed_demo --prazos-curtos
   ```

3. Em um terminal separado, deixe o processamento de prazos rodando:

   ```powershell
   python backend\manage.py processar_prazos --loop 15
   ```

Senha de todos os usuários de exemplo: `Demo@12345`.

| Perfil | E-mail |
|---|---|
| Admin (`/admin`) | `admin@exemplo.com` |
| Empresa aprovada | `empresa1@exemplo.com`, `empresa2@exemplo.com` |
| Empresa pendente na fila | `empresa.pendente@exemplo.com` |
| Prestador aprovado (com PIX) | `prestador1@exemplo.com`, `prestador2@exemplo.com`, `prestador3@exemplo.com` |
| Prestador pendente na fila | `prestador.pendente@exemplo.com` |

Os dados de exemplo são fictícios (CPFs e CNPJs válidos gerados, e-mails `@exemplo.com`). Rodar `seed_demo` de novo não duplica nada.

## Simular a localização no navegador (check-in)

O check-in só é aceito a até 150 m da vaga. Para simular a posição do prestador:

1. Abra o app como prestador e pressione `F12` (DevTools).
2. Abra o menu `⋮` → **More tools** → **Sensors** (ou `Ctrl+Shift+P` e digite "Show Sensors").
3. Em **Location**, escolha **Other…** e informe a latitude e a longitude da vaga (por exemplo, `-23.550520` e `-46.633308` para a vaga da Praça da Sé). Para simular a falta, deixe a localização em outro ponto ou não faça o check-in.
4. Permita a localização no navegador quando ele pedir e atualize a página.

## Os 12 passos

Os passos 2 a 4 podem usar os cadastros novos que você fizer na hora ou os pendentes criados pelo `seed_demo`.

1. **Prazos curtos (admin).** Entre em `/admin` com `admin@exemplo.com`, abra "Parâmetros da plataforma" e confira os valores: antecedência mínima 1 min, encerramento de candidaturas 1 min, tolerância de falta 2 min, contestação 2 min e check-out automático 2 min. O `seed_demo --prazos-curtos` já os aplica; a alteração fica auditada.
2. **Cadastro da empresa.** Em "Cadastrar como empresa", informe o CNPJ; os dados vêm da BrasilAPI. (Alternativa: use `empresa.pendente@exemplo.com`.)
3. **Cadastro do prestador.** Em "Cadastrar como prestador", preencha os dados, envie documento e selfie e informe a chave PIX. (Alternativa: use `prestador.pendente@exemplo.com`.)
4. **Triagem.** No admin, abra a fila de verificação e aprove a empresa e o prestador.
5. **Publicar e pagar.** Como `empresa1@exemplo.com`, crie uma vaga de R$ 100,00 para 2 pessoas com início daqui a poucos minutos (mínimo de 1 min de antecedência) e pague em custódia. A vaga só é publicada depois do pagamento.
6. **Busca.** Como `prestador1@exemplo.com`, busque e filtre vagas. A mais próxima mostra "Você recebe R$ 97,00" e o selo "Pagamento garantido".
7. **Candidaturas.** Candidate-se com `prestador1@exemplo.com` (prestador A) e `prestador2@exemplo.com` (prestador B) e acompanhe o status em "Meus trabalhos". As candidaturas fecham 1 min antes do início.
8. **Aprovação.** Como empresa, aprove os dois candidatos antes do encerramento.
9. **Check-in.** No horário, o prestador A simula a localização da vaga (DevTools → Sensors, veja acima) e faz o check-in, a até 150 m.
10. **Falta.** O prestador B não comparece. Em até 2 min depois do início, o `processar_prazos` registra a falta, reabre a posição e avisa a empresa.
11. **Check-out e confirmação.** O prestador A faz o check-out. A empresa confirma a presença, ou espera os 2 min da janela de contestação para a aprovação automática.
12. **Carteira e auditoria.** A carteira do prestador A mostra R$ 97,00 liberados. No admin, veja a trilha de auditoria ("Transições de estado") e o estorno da posição não usada.

## Dicas

- Se a demonstração travar em algum prazo, confira se o `processar_prazos --loop 15` está rodando.
- Para voltar aos prazos padrão, edite os valores em "Parâmetros da plataforma" no admin.
- Para recomeçar do zero, recrie o banco (`docker compose down -v` e `docker compose up -d`), rode `migrate` e depois `seed_demo` de novo.
