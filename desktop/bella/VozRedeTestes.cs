using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Text;

namespace Bella {
    static class VozRedeTestes {
        sealed class Motor : HttpMessageHandler {
            public int Calls;
            public bool Waiting;
            public readonly TaskCompletionSource<bool> Started=new TaskCompletionSource<bool>();
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                Calls++; Started.TrySetResult(true);
                if(Waiting) await Task.Delay(Timeout.Infinite,token).ConfigureAwait(false);
                return new HttpResponseMessage(HttpStatusCode.OK) { Content=new StringContent("{\"audio_base64\":\"SUQz\",\"mime\":\"audio/mpeg\"}",Encoding.UTF8,"application/json") };
            }
        }
        static void Check(bool ok,string message) { if(!ok) throw new Exception(message); }
        public static void Run() { Test().GetAwaiter().GetResult(); }
        static async Task Test() {
            string key="bella_"+new string('x',43);
            // Cancelar a voz não cancela nem repete o comando que produz o texto.
            var command=new Motor();
            using(var stop=new CancellationTokenSource()) {
                stop.Cancel();
                using(var client=new Client("https://test.invalid",key,command,stop.Token)) {
                    Check(await client.Send("consulta",null).ConfigureAwait(false)!=null && command.Calls==1,"cancelamento de voz preserva pedido e resultado");
                }
            }
            foreach(bool local in new[] {true,false}) {
                var fast=new Motor();
                using(var client=new Client("https://test.invalid",key,fast)) {
                    var task=local ? client.LocalVoice("aberto") : client.ResponseVoice("resposta");
                    Check(await Task.WhenAny(task,Task.Delay(2000)).ConfigureAwait(false)==task,"voz pronta retorna sem espera artificial");
                    var result=await task.ConfigureAwait(false);
                    Check(result.audio_base64=="SUQz" && fast.Calls==1,"áudio rápido preservado sem repetição");
                }
                var slow=new Motor {Waiting=true};
                using(var stop=new CancellationTokenSource())
                using(var client=new Client("https://test.invalid",key,slow,stop.Token)) {
                    var task=local ? client.LocalVoice("aberto") : client.ResponseVoice("resposta");
                    await slow.Started.Task.ConfigureAwait(false);
                    Check(!task.IsCompleted,"voz lenta aguarda sem bloquear a thread chamadora");
                    stop.Cancel();
                    bool canceled=false;
                    try { await task.ConfigureAwait(false); } catch(OperationCanceledException) {canceled=true;}
                    Check(canceled && slow.Calls==1,"interromper cancela voz pendente sem repetir o pedido");
                }
                var skipped=new Motor();
                using(var stop=new CancellationTokenSource()) {
                    stop.Cancel();
                    using(var client=new Client("https://test.invalid",key,skipped,stop.Token)) {
                        bool canceled=false;
                        try { if(local) await client.LocalVoice("aberto").ConfigureAwait(false); else await client.ResponseVoice("resposta").ConfigureAwait(false); }
                        catch(OperationCanceledException) {canceled=true;}
                        Check(canceled && skipped.Calls==0,"voz já interrompida não inicia nova chamada ao servidor");
                    }
                }
            }
        }
    }
}
