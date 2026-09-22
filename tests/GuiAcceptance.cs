using System;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
class GuiAcceptance {
 [STAThread] static int Main(string[] args) {
  var path=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","NBA2K21 Offline Tool.exe");
  var asm=Assembly.LoadFrom(Path.GetFullPath(path));
  var t=asm.GetType("V2FLSEngine.Gui.MainForm");
  using(var form=(Form)Activator.CreateInstance(t,true)) {
   var flags=BindingFlags.NonPublic|BindingFlags.Instance;
   ((Timer)t.GetField("_pollTimer",flags).GetValue(form)).Stop();
   form.ShowInTaskbar=false;form.Opacity=0;form.Show();Application.DoEvents();form.Hide();
   Console.WriteLine("GUI_STARTED root="+t.GetField("_root",flags).GetValue(form));
   var buttons=(Button[])t.GetField("_actionButtons",flags).GetValue(form);
   foreach(var b in buttons) if(((string)b.Tag).StartsWith("park-meta-")) {
    var label=(string)t.GetMethod("ActionLabel",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new object[]{(string)b.Tag});
    if(label!=b.Text || !b.Enabled)throw new Exception("Button label/gating mismatch "+b.Tag);
    Console.WriteLine("BUTTON "+b.Tag+" "+b.Text);
   }
   if(args.Length==0)return 0;
   object res=t.GetMethod("RunProcess",flags).Invoke(form,new object[]{args[0],false});
   var rt=res.GetType();Console.WriteLine(rt.GetField("Stdout").GetValue(res));Console.Error.WriteLine(rt.GetField("Stderr").GetValue(res));
   return (int)rt.GetField("ExitCode").GetValue(res);
  }
 }
}
