using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    // PCM mono 16 kHz / 16 bits, compatível com Vosk e com a API da Bella.
    public sealed class Microphone : IDisposable {
        [StructLayout(LayoutKind.Sequential, Pack=2)] struct Format {
            public ushort tag, channels; public uint rate, average; public ushort align, bits, extra;
        }
        [StructLayout(LayoutKind.Sequential)] struct Header {
            public IntPtr data; public uint length, recorded; public UIntPtr user;
            public uint flags, loops; public IntPtr next; public UIntPtr reserved;
        }
        [DllImport("winmm.dll")] static extern uint waveInOpen(out IntPtr h, uint device, ref Format fmt, IntPtr callback, IntPtr instance, uint flags);
        [DllImport("winmm.dll")] static extern uint waveInPrepareHeader(IntPtr h, IntPtr p, uint size);
        [DllImport("winmm.dll")] static extern uint waveInUnprepareHeader(IntPtr h, IntPtr p, uint size);
        [DllImport("winmm.dll")] static extern uint waveInAddBuffer(IntPtr h, IntPtr p, uint size);
        [DllImport("winmm.dll")] static extern uint waveInStart(IntPtr h);
        [DllImport("winmm.dll")] static extern uint waveInReset(IntPtr h);
        [DllImport("winmm.dll")] static extern uint waveInClose(IntPtr h);
        IntPtr device;
        readonly List<IntPtr> headers = new List<IntPtr>();
        volatile bool running;
        Task reader;
        readonly uint headerSize = (uint)Marshal.SizeOf(typeof(Header));
        public void Start(Action<byte[]> data, Action<string> error) {
            var fmt = new Format { tag=1, channels=1, rate=16000, average=32000, align=2, bits=16 };
            Check(waveInOpen(out device, UInt32.MaxValue, ref fmt, IntPtr.Zero, IntPtr.Zero, 0));
            try {
                for (int i=0; i<6; i++) {
                    var h = new Header { data=Marshal.AllocHGlobal(3200), length=3200 };
                    var p = Marshal.AllocHGlobal((int)headerSize);
                    Marshal.StructureToPtr(h, p, false); headers.Add(p);
                    Check(waveInPrepareHeader(device, p, headerSize)); Check(waveInAddBuffer(device, p, headerSize));
                }
                Check(waveInStart(device)); running=true;
                reader=Task.Run(() => {
                    try {
                        while (running) {
                            foreach (var p in headers) {
                                if (!running) break;
                                var h=(Header)Marshal.PtrToStructure(p, typeof(Header));
                                if ((h.flags & 1)==0) continue;
                                var bytes=new byte[h.recorded]; Marshal.Copy(h.data, bytes, 0, bytes.Length);
                                if (bytes.Length>0) data(bytes);
                                if (running) Check(waveInAddBuffer(device, p, headerSize));
                            }
                            Thread.Sleep(10);
                        }
                    } catch { running=false; error("O microfone parou. Pause e ative a escuta novamente."); }
                });
            } catch { Dispose(); throw; }
        }
        static void Check(uint code) { if(code!=0) throw new InvalidOperationException("Não consegui abrir o microfone (Windows " + code + "). Confira a permissão e o dispositivo padrão."); }
        public void Dispose() {
            running=false;
            if(reader!=null && !reader.Wait(3000)) throw new InvalidOperationException("O microfone ainda está encerrando.");
            if(device==IntPtr.Zero) return;
            waveInReset(device);
            foreach(var p in headers) {
                waveInUnprepareHeader(device,p,headerSize);
                var h=(Header)Marshal.PtrToStructure(p,typeof(Header));
                Marshal.FreeHGlobal(h.data); Marshal.FreeHGlobal(p);
            }
            headers.Clear(); waveInClose(device); device=IntPtr.Zero;
        }
    }

    public interface IWake : IDisposable { bool Hear(byte[] pcm); void Reset(); }
    public sealed class Capture {
        public enum Mode { Paused, Listening, Recording, Processing, Speaking }
        public Mode State { get; private set; }
        public event Action<byte[]> RequestReady;
        public event Action<Mode> Changed;
        readonly object gate = new object();
        readonly IWake wake;
        MemoryStream record=new MemoryStream();
        double elapsed, lastVoice;
        bool heardVoice;
        public int Threshold = 220;
        public Capture(IWake detector) { wake=detector; State=Mode.Paused; }
        void Set(Mode mode) { State=mode; if(Changed!=null) Changed(mode); }
        public void Listen() { lock(gate) { record.SetLength(0); wake.Reset(); Set(Mode.Listening); } }
        public void Pause() { lock(gate) { record.SetLength(0); Set(Mode.Paused); } }
        public void Begin() { lock(gate) { if(State==Mode.Processing) return; BeginInside(); } }
        public void Speaking() { lock(gate) Set(Mode.Speaking); }
        public void Processing() { lock(gate) Set(Mode.Processing); }
        void BeginInside() {
            record.SetLength(0); elapsed=lastVoice=0; heardVoice=false;
            Set(Mode.Recording);
        }
        public void Feed(byte[] pcm) {
            byte[] ready=null;
            lock(gate) {
                if(State==Mode.Listening) {
                    if(wake.Hear(pcm)) BeginInside();
                } else if(State==Mode.Recording) {
                    record.Write(pcm,0,pcm.Length); elapsed+=(double)pcm.Length/32000;
                    if(Energy(pcm)>Threshold) { lastVoice=elapsed; heardVoice=true; }
                    if(elapsed>=29 || (heardVoice && elapsed-lastVoice>=1.3 && elapsed>=1)) {
                        ready=Wave(record.ToArray()); record.SetLength(0); Set(Mode.Processing);
                    } else if(!heardVoice && elapsed>=6) { record.SetLength(0); wake.Reset(); Set(Mode.Listening); }
                }
            }
            if(ready!=null && RequestReady!=null) RequestReady(ready);
        }
        public static double Energy(byte[] pcm) {
            double sum=0; for(int i=0;i+1<pcm.Length;i+=2) { double n=(short)(pcm[i]|pcm[i+1]<<8); sum+=n*n; }
            return pcm.Length==0?0:Math.Sqrt(sum/(pcm.Length/2));
        }
        public static byte[] Wave(byte[] pcm) {
            using(var s=new MemoryStream()) using(var w=new BinaryWriter(s)) {
                w.Write(System.Text.Encoding.ASCII.GetBytes("RIFF")); w.Write(pcm.Length+36);
                w.Write(System.Text.Encoding.ASCII.GetBytes("WAVEfmt ")); w.Write(16); w.Write((short)1); w.Write((short)1);
                w.Write(16000); w.Write(32000); w.Write((short)2); w.Write((short)16);
                w.Write(System.Text.Encoding.ASCII.GetBytes("data")); w.Write(pcm.Length); w.Write(pcm); return s.ToArray();
            }
        }
    }
}
