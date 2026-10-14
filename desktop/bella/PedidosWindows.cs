using System;
using System.Threading.Tasks;
using System.Text.RegularExpressions;

namespace Bella {
    public sealed class PedidosWindows {
        string tokenSolo;
        bool ultimoLocal;
        public void Cancelar() { tokenSolo=null; ultimoLocal=true; }
        public async Task<Reply> Enviar(string text,byte[] audio,Arquivos arquivos,Func<Client> cliente,Action<string> ouvido,Func<bool> continuar=null) {
            bool viaAudio=audio!=null;
            if(viaAudio) {
                using(var c=cliente()) text=(await c.Transcribe(audio)).ouvido;
                if(continuar!=null && !continuar()) throw new OperationCanceledException();
                if(ouvido!=null) ouvido(text);
            }
            if(continuar!=null && !continuar()) throw new OperationCanceledException();
            var botao=Regex.Match(text ?? "",@"^/solo-escolher ([a-f0-9]{32}) (\d+)$");
            if(botao.Success) {
                if(botao.Groups[1].Value!=tokenSolo) {
                    arquivos.Cancelar(); ultimoLocal=true;
                    return new Reply { CodigoVoz="expirou", texto="Essa opção antiga não é mais a escolha atual. Faça o pedido novamente.", falar="Essa opção expirou. Faça o pedido novamente." };
                }
                text=botao.Groups[2].Value;
            } else if(ultimoLocal && !arquivos.TemEscolha && Arquivos.EhResposta(text)) {
                return new Reply { CodigoVoz="expirou", texto="Não há uma escolha de arquivo pendente. Faça o pedido novamente.", falar="Não há uma escolha de arquivo pendente." };
            }
            var reply=await arquivos.Processar(text);
            if((reply==null || reply.CodigoVoz=="erro" || reply.CodigoVoz=="vazio") && arquivos.PodeInterpretar(text)) {
                InterpretacaoComando escolha=null;
                try { using(var c=cliente()) escolha=await c.InterpretarComando(text,arquivos.CatalogoComandos); }
                catch(UnauthorizedAccessException) { throw; }
                catch(Exception) { } // Sem IA, oferece os comandos locais; não vira lançamento financeiro.
                if(continuar!=null && !continuar()) throw new OperationCanceledException();
                reply=await arquivos.Interpretar(escolha,text);
            }
            if(reply==null && arquivos.PedidoLocal(text)) reply=await arquivos.Interpretar(null,text);
            if(reply==null) {
                arquivos.Cancelar(); tokenSolo=null; ultimoLocal=false;
                using(var c=cliente()) reply=await c.Send(text,null,viaAudio);
                tokenSolo=Guid.NewGuid().ToString("N");
                foreach(var o in reply.opcoes ?? new Opcao[0]) o.comando="/solo-escolher "+tokenSolo+" "+o.numero;
                return reply;
            }
            tokenSolo=null; ultimoLocal=true;
            // O resultado fica no computador. Só um código fixo pede a voz atual;
            // sem conexão/chave, a resposta continua disponível na voz do Windows.
            try {
                using(var c=cliente()) {
                    var voz=await c.LocalVoice(reply.CodigoVoz);
                    reply.falar=voz.falar; reply.audio_base64=voz.audio_base64; reply.mime=voz.mime;
                }
            } catch(Exception) { }
            return reply;
        }
    }
}
