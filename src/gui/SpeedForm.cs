using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace V2FLSEngine.Gui
{
    internal sealed class SpeedForm : Form
    {
        private readonly string root;
        private Process controller;
        private readonly Label target = new Label();
        private readonly Label state = new Label();
        private readonly Label multiplier = new Label();
        private readonly Label telemetry = new Label();
        private readonly Label detail = new Label();
        private readonly Button[] presets = new Button[5];
        private readonly Timer timer = new Timer();
        private bool ready;

        internal SpeedForm(string projectRoot)
        {
            root = projectRoot;
            Text = "遊戲時間控制 · 實驗性";
            Size = new Size(590, 350);
            MinimumSize = Size;
            StartPosition = FormStartPosition.CenterParent;
            BackColor = Color.FromArgb(30,30,30);
            ForeColor = Color.White;
            Font = new Font("Segoe UI", 10F);
            var panel = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(15), AutoScroll = true };
            Controls.Add(panel);
            var note = new Label { Text = "Process Time Multiplier · 與遊戲內「比賽速度」數值分開", Width = 540, Height = 34 };
            panel.Controls.Add(note);
            foreach (var pair in new[] { Tuple.Create(target,"Target: —"), Tuple.Create(state,"Speed Engine: Not Loaded"), Tuple.Create(multiplier,"Multiplier: 1.00x"), Tuple.Create(telemetry,"Clock telemetry: —"), Tuple.Create(detail,"狀態：待連線") })
            {
                pair.Item1.Text=pair.Item2;pair.Item1.Width=540;pair.Item1.Height=27;panel.Controls.Add(pair.Item1);
            }
            telemetry.Height=50;
            var row = new FlowLayoutPanel { Width=540, Height=47, WrapContents=false };
            var enable = new Button { Text="啟用遊戲變速", Width=140, Height=35 };
            enable.Click+=(s,e)=>StartController();row.Controls.Add(enable);
            var disable = new Button { Text="停用 / 1.00x", Width=140, Height=35 };
            disable.Click+=(s,e)=>StopController();row.Controls.Add(disable);
            panel.Controls.Add(row);
            var choices1 = new FlowLayoutPanel { Width=540, Height=44, WrapContents=false };
            var choices2 = new FlowLayoutPanel { Width=540, Height=44, WrapContents=false };
            string[] labels={"0.10x 思考模式","0.25x","0.50x","0.75x","1.00x 正常"};
            string[] values={"0.10","0.25","0.50","0.75","1.00"};
            int[] widths={155,115,115,115,155};
            for(int i=0;i<5;i++)
            {
                var value=values[i];var b=new Button {Text=labels[i],Width=widths[i],Height=36,Enabled=false};
                b.Click+=(s,e)=>Send("SET "+value);presets[i]=b;(i<3?choices1:choices2).Controls.Add(b);
            }
            panel.Controls.Add(choices1);panel.Controls.Add(choices2);
            timer.Interval=1000;timer.Tick+=(s,e)=> {if(ready)Send("STATUS");};
        }

        private void Send(string command)
        {
            try
            {
                if(controller==null || controller.HasExited)throw new InvalidOperationException("控制器未執行");
                controller.StandardInput.WriteLine(command);controller.StandardInput.Flush();
            }
            catch(Exception ex){ShowError(ex.Message);}
        }
        private void StartController()
        {
            if(controller!=null && !controller.HasExited)return;
            var python=Path.Combine(root,"runtime","python","python.exe");
            var script=Path.Combine(root,"speed_engine","controller.py");
            var dll=Path.Combine(root,"release","speed_engine","SpeedEngine64.dll");
            if(!File.Exists(python)||!File.Exists(script)||!File.Exists(dll)){ShowError("Speed Engine 元件不完整；請重建專案。");return;}
            try
            {
                ready=false;state.Text="Speed Engine: Starting";
                var psi=new ProcessStartInfo(python,"-I -B \""+script+"\" --game")
                { WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true };
                controller=new Process { StartInfo=psi,EnableRaisingEvents=true };
                controller.OutputDataReceived+=(s,e)=>Receive(e.Data,false);
                controller.ErrorDataReceived+=(s,e)=>Receive(e.Data,true);
                controller.Exited+=(s,e)=>{if(!IsDisposed && IsHandleCreated)BeginInvoke(new Action(()=> { ready=false;timer.Stop();SetPresetEnabled(false);state.Text="Speed Engine: Not Loaded"; }));};
                controller.Start();controller.BeginOutputReadLine();controller.BeginErrorReadLine();
            }
            catch(Exception ex){ShowError(ex.Message);}
        }
        private void Receive(string line,bool error)
        {
            if(string.IsNullOrEmpty(line)||IsDisposed||!IsHandleCreated)return;
            BeginInvoke(new Action(()=>HandleLine(line,error)));
        }
        private void HandleLine(string line,bool error)
        {
            if(error){detail.Text="錯誤詳情："+line;return;}
            int gap=line.IndexOf(' ');
            if(gap<0)return;
            var tag=line.Substring(0,gap);
            if(tag=="ERROR"){ShowError(line.Substring(gap+1));return;}
            if(tag!="READY"&&tag!="STATUS"&&tag!="SET"&&tag!="QUIT")return;
            try
            {
                var json=line.Substring(gap+1);
                var j=SimpleJson.Parse(json);
                string status=j.GetStr("status");
                string active=j.GetStr("active");
                string requested=j.GetStr("requested");
                string seq=j.GetStr("seq"),ack=j.GetStr("ack");
                string mask=j.GetStr("hook_mask");
                if(tag=="READY")
                {
                    var pid=j.GetStr("pid");target.Text="Target: NBA2K21.exe · PID "+pid;
                    ready=(status=="2"||status=="3") && (Convert.ToInt32(mask)&9)==9;
                    SetPresetEnabled(ready);if(ready)timer.Start();
                }
                if(tag=="SET" && (seq!=ack||active!=requested)){ShowError("倍率切換未獲確認；控制器將停止並還原 1.00x。");return;}
                state.Text="Speed Engine: "+(ready?(status=="3"?"Active":"Ready"):"Error");
                multiplier.Text="Multiplier: "+active+"x";
                int bits=Convert.ToInt32(mask);
                var names=new[] {"QPC","GTC64","GTC","timeGetTime"};
                var items=new string[4];
                for(int i=0;i<4;i++)items[i]=names[i]+": "+(((bits&(1<<i))!=0)?"ACTIVE":"NOT USED");
                telemetry.Text=string.Join(" · ",items);
                detail.Text="Ack: "+ack+" / "+seq;
                if(tag=="QUIT"){ready=false;timer.Stop();SetPresetEnabled(false);state.Text="Speed Engine: Not Loaded";}
            }
            catch(Exception ex){ShowError("控制器回覆無效："+ex.Message);}
        }
        private void SetPresetEnabled(bool enabled){foreach(var b in presets)b.Enabled=enabled;}
        private void ShowError(string message){ready=false;timer.Stop();SetPresetEnabled(false);state.Text="Speed Engine: Error";detail.Text=message;}
        private void StopController()
        {
            if(controller!=null && !controller.HasExited)Send("QUIT");
            ready=false;timer.Stop();SetPresetEnabled(false);
        }
        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            StopController();
            if(controller!=null && !controller.HasExited)
            {
                if(!controller.WaitForExit(2200))controller.Kill();
                controller.Dispose();
            }
            timer.Dispose();
            base.OnFormClosing(e);
        }
    }
}
