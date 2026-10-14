using System;
using System.Threading.Tasks;
using System.Text.RegularExpressions;

namespace Bella {
    public sealed class PedidosWindows {
        string tokenSolo;
        bool ultimoLocal;
        public void Cancelar() { tokenSolo=null; ultimoLocal=true; }
        public async Task<Reply> Enviar(string text,byte[] audio,Arquivos arquivos,Func<Client> cliente,Action<string> ouvido,Func<bool> continuar=null,Action<Reply> resultado=null) {
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
                    var expirada=new Reply { CodigoVoz="expirou", texto="Essa opção antiga não é mais a escolha atual. Faça o pedido novamente.", falar="Essa opção expirou. Faça o pedido novamente." };
                    if(resultado!=null) resultado(expirada);
                    return expirada;
                }
                text=botao.Groups[2].Value;
            } else if(ultimoLocal && !arquivos.TemEscolha && Arquivos.EhResposta(text)) {
                var expirada=new Reply { CodigoVoz="expirou", texto="Não há uma escolha de arquivo pendente. Faça o pedido novamente.", falar="Não há uma escolha de arquivo pendente." };
                if(resultado!=null) resultado(expirada);
                return expirada;
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
                if(continuar!=null && !continuar()) throw new OperationCanceledException();
                if(resultado!=null) resultado(reply);
                if(!String.IsNullOrEmpty(reply.voz_id)) {
                    try { using(var c=cliente()) CopiarVoz(reply,await c.ResponseVoice(reply.voz_id)); }
                    catch(Exception) { } // A operação já terminou. Mantém a fala local, sem reenviar o pedido.
                }
                return reply;
            }
            tokenSolo=null; ultimoLocal=true;
            if(continuar!=null && !continuar()) throw new OperationCanceledException();
            if(resultado!=null) resultado(reply);
            // O resultado fica no computador. Só um código fixo pede a voz atual;
            // sem conexão/chave, a resposta continua disponível na voz do Windows.
            try {
                using(var c=cliente()) {
                    var voz=await c.LocalVoice(reply.CodigoVoz);
                    CopiarVoz(reply,voz);
                }
            } catch(Exception) { }
            return reply;
        }
        static void CopiarVoz(Reply destino,Reply voz) {
            destino.falar=voz.falar ?? destino.falar;
            destino.audio_base64=voz.audio_base64; destino.mime=voz.mime;
        }
    }
}
