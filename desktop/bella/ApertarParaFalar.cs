using System;
using System.Windows.Forms;

namespace Bella {
    // Observa somente o atalho escolhido. Não registra o que o usuário digita.
    public static class ApertarParaFalar {
        public static bool TeclaValida(int tecla) {
            return (tecla>=48 && tecla<=90 && (tecla<=57 || tecla>=65))
                || (tecla>=96 && tecla<=123) || (tecla>=124 && tecla<=135)
                || tecla==32 || (tecla>=33 && tecla<=40) || tecla==45 || tecla==46
                || tecla==8 || tecla==13 || tecla==19 || tecla==20 || tecla==145
                || (tecla>=186 && tecla<=192) || (tecla>=219 && tecla<=222);
        }
        public static void Validar(int tecla,int modificadores,int segundos) {
            if(!TeclaValida(tecla) || modificadores<0 || modificadores>7)
                throw new InvalidOperationException("Escolha uma tecla, opcionalmente com Ctrl, Alt ou Shift.");
            if(segundos<1 || segundos>30)
                throw new InvalidOperationException("Escolha de 1 a 30 segundos para ativar a fala.");
        }
        public static string Nome(int tecla,int modificadores) {
            string nome=tecla==32 ? "Espaço" : ((Keys)tecla).ToString();
            return ((modificadores&2)!=0 ? "Ctrl + " : "") + ((modificadores&1)!=0 ? "Alt + " : "")
                + ((modificadores&4)!=0 ? "Shift + " : "") + nome;
        }
    }

    internal enum AcaoTecla { Nenhuma, Comecar, Enviar, Cancelar }
    internal sealed class EsperaTecla {
        bool liberar=true, ativa;
        double inicio=-1, ultimo=-1;
        public int Restantes { get; private set; }
        public bool Contando { get { return inicio>=0 && !ativa; } }
        public void Reiniciar() { liberar=true; ativa=false; inicio=ultimo=-1; Restantes=0; }
        public AcaoTecla Atualizar(bool habilitada,bool pressionada,double agora,int segundos) {
            bool interrompida=ultimo>=0 && (agora-ultimo>500 || agora<ultimo);
            ultimo=agora;
            if(!habilitada || interrompida) {
                bool cancelar=ativa;
                liberar=true; ativa=false; inicio=-1; Restantes=0;
                return cancelar ? AcaoTecla.Cancelar : AcaoTecla.Nenhuma;
            }
            if(!pressionada) {
                bool enviar=ativa;
                liberar=false; ativa=false; inicio=-1; Restantes=0;
                return enviar ? AcaoTecla.Enviar : AcaoTecla.Nenhuma;
            }
            if(liberar || ativa) return AcaoTecla.Nenhuma;
            if(inicio<0) inicio=agora;
            Restantes=Math.Max(0,(int)Math.Ceiling(segundos-(agora-inicio)/1000));
            if(agora-inicio<segundos*1000) return AcaoTecla.Nenhuma;
            ativa=true; Restantes=0;
            return AcaoTecla.Comecar;
        }
    }
}
