# INVENTÁRIO — Registro de bags da produção

Aplicação desktop para Windows, feita em Python com Tkinter e SQLite. Não usa
Node.js nem requer instalação de privilégios administrativos. O projeto
Streamlit e os arquivos CSV já existentes na pasta acima permanecem intactos.

## Requisitos

- Python 3.10 ou superior, com Tkinter habilitado.
- `openpyxl` para gerar relatórios `.xlsx`.

No terminal do VS Code, entre na raiz `Downloads\INVENTARIO_FORTLEV` do projeto
(um nível acima da pasta `inventario_desktop`) e execute:

```powershell
python -m pip install --user -r .\inventario_desktop\requirements.txt
python -m inventario_desktop
```

Ou abra `inventario_desktop\iniciar_inventario.bat` no Explorador de Arquivos.
O atalho também pode ser iniciado pelo terminal:

```powershell
.\inventario_desktop\iniciar_inventario.bat
```

## Versão para navegador

Para abrir a tela de registro no navegador deste PC, execute:

```powershell
python -m inventario_desktop.web_app
```

Ou abra `inventario_desktop\iniciar_inventario_web.bat`. Essa opção fica
disponível somente no próprio PC em `http://127.0.0.1:8765`.

### Acesso pelo celular na rede local

Para o piloto, conecte o celular e o PC à mesma rede Wi-Fi privada e execute
`inventario_desktop\iniciar_inventario_web_rede.bat`. O atalho pede o IPv4
privado do PC (consulte `ipconfig`) e vincula o servidor somente a esse
adaptador. Abra no celular o endereço `http://IP_DO_PC:8765`, digite o material,
informe o peso e bipe o ID único da etiqueta. Um leitor
Bluetooth configurado como teclado HID pareado com o celular também pode
preencher os campos de código e ID da etiqueta. IDs já registrados são
recusados, mesmo quando diferem apenas em maiúsculas/minúsculas ou espaços nas
pontas. O registro é gravado no banco SQLite desse PC;
não é enviado ao GitHub. A tela Histórico do aplicativo desktop pode ser
atualizada ao abrir/selecionar a aba.

Se o Firewall do Windows perguntar, permita o acesso somente em redes privadas.
Qualquer dispositivo na rede permitida poderá registrar bags. Não encaminhe a
porta do roteador nem exponha esse servidor na internet. O modo de rede local
usa HTTP sem criptografia e é apenas um piloto em rede confiável. Para uso de
produção, solicite à TI um servidor interno com HTTPS, autenticação e
configuração de firewall apropriada.

O GitHub pode guardar o código-fonte, mas não hospeda este servidor Python nem
armazena os registros. O servidor web só deve ser iniciado em um PC aprovado e
os dados continuam no banco local descrito abaixo.

No Streamlit, use a senha padrão `10203040` na barra lateral para entrar como
administrador. A senha de acesso do Streamlit é independente da senha PBKDF2
que o aplicativo desktop mantém no banco local. Para substituir a senha padrão
em um deploy Streamlit, configure `FORTLEV_ADMIN_PASSWORD` em **App settings >
Secrets**; não publique uma senha privada no código. No navegador, o
administrador pode acessar o histórico (com filtros e exportação Excel) ou
gerenciar materiais. No histórico, um registro individual pode ser selecionado
pelo número e excluído após confirmação. A tela de registro continua sem
senha. O Cloud não acessa o banco local do PC e não oferece persistência
confiável para o SQLite local; use um banco hospedado para dados compartilhados.

Se o Python padrão não tiver Tkinter, use um Python instalado e habilitado pela
TI. A aplicação não solicita nem contorna permissões administrativas.

## Como operar

1. Na primeira execução, os três materiais iniciais são inseridos no banco:
   `4000001733`, `4000000416` e `4000000417`, todos na categoria PVC.
2. Na aba **NOVO REGISTRO**, bipar o código do material; o coletor HID funciona
   como teclado.
3. Após o ENTER do código, o cursor vai para o peso.
4. Após o ENTER do peso, o cursor vai para o ID da etiqueta. Bipe o ID único;
   se ele já tiver sido registrado, o sistema avisa e não permite duplicá-lo.
   Após o ENTER do ID, o foco vai para **REGISTRAR BAG**. A leitura
   não salva sozinha: confirme com outro ENTER ou clique no botão. Um ENTER
   repetido em menos de meio segundo é ignorado como repetição do coletor.
5. Código, ID da etiqueta, peso, descrição e categoria ficam salvos
   individualmente. Depois do sucesso, os campos são limpos e o foco volta ao
   código.
6. **HISTÓRICO** permite pesquisa, datas inicial/final em `AAAA-MM-DD`, resumo,
   exportação Excel e criação manual de backup.
7. **MATERIAIS · ADMIN** permite cadastrar, editar e ativar/desativar materiais.
   Na primeira abertura, crie uma senha de administrador (mínimo 8 caracteres).
   O banco guarda somente o hash PBKDF2 e o salt, não a senha.

## Dados, data/hora e backups

O SQLite fica fora da pasta do código:

```text
%LOCALAPPDATA%\Fortlev\Inventario\inventario.db
```

No primeiro uso, os registros começam vazios. Os CSVs preexistentes **não são
importados** para evitar misturar registros antigos com as novas bipagens. O
registro usa o fuso `America/Sao_Paulo`; se a base de fusos não estiver
disponível no Windows, usa UTC-03:00, que corresponde ao horário civil atual de
São Paulo.

Use **CRIAR BACKUP DO BANCO** regularmente e guarde a cópia em um local aprovado
pela empresa. Para recuperar, abra **MATERIAIS · ADMIN**, autentique-se e use
**RESTAURAR BACKUP**. A aplicação valida a integridade do arquivo, pede
confirmação e cria automaticamente uma cópia do banco atual antes de restaurar.

## Limites importantes

Este modo SQLite é adequado para um computador por vez. **Não compartilhe o
arquivo `.db` em uma pasta de rede para acessos simultâneos**: isso pode causar
problemas de bloqueio ou integridade. Para vários computadores, a TI precisa
disponibilizar um banco central e uma conexão de rede aprovada.

Os campos `INVENTARIO_SCANNER_PREFIX` e `INVENTARIO_SCANNER_SUFFIX` permitem
remover texto fixo adicional do peso, se o coletor enviar esse conteúdo. O
ENTER automático de cada leitura é tratado separadamente da confirmação. O
comportamento deve ser confirmado com o modelo real do coletor antes do uso na
produção.

## Testes

Na raiz do projeto `Downloads\INVENTARIO_FORTLEV`, execute:

```powershell
python -m unittest discover -s .\inventario_desktop\tests -v
```

Os testes usam um banco temporário e não alteram o banco operacional.
