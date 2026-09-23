using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace V2FLSEngine.Gui
{
    internal sealed class MainForm : Form
    {
        // ---- Dark theme palette ----
        private static readonly Color C_BG = Color.FromArgb(30, 30, 30);
        private static readonly Color C_PANEL = Color.FromArgb(37, 37, 38);
        private static readonly Color C_PANEL_ALT = Color.FromArgb(45, 45, 48);
        private static readonly Color C_BORDER = Color.FromArgb(63, 63, 70);
        private static readonly Color C_TEXT = Color.FromArgb(212, 212, 212);
        private static readonly Color C_TEXT_DIM = Color.FromArgb(156, 156, 156);
        private static readonly Color C_ACCENT = Color.FromArgb(78, 201, 176);
        private static readonly Color C_OK = Color.FromArgb(106, 153, 85);
        private static readonly Color C_WARN = Color.FromArgb(198, 120, 221);
        private static readonly Color C_BAD = Color.FromArgb(244, 135, 113);
        private static readonly Color C_BTN = Color.FromArgb(51, 51, 55);
        private static readonly Color C_BTN_HOVER = Color.FromArgb(62, 62, 66);
        private static readonly Color C_BTN_BORDER = Color.FromArgb(86, 86, 92);

        // ---- Controls ----
        private Label _lblConnGame, _lblConnSha, _lblConnProc, _lblConnTime;
        private Label _lblName, _lblTeam, _lblFace, _lblBaseline, _lblSource;
        private Label _lblStats;
        private Label _lblMc, _lblHo;
        private Button _btnMcEnable, _btnMcDisable, _btnHoEnable, _btnHoDisable;
        private CheckBox _chkDebug;
        private RichTextBox _log;
        private Button[] _actionButtons;

        // ---- Roster browser (mode-agnostic player source) ----
        private ComboBox _cmbRosterTeam, _cmbRosterPlayer;
        private Button _btnRosterRead;
        private List<int> _rosterTeamIndices = new List<int>();
        private List<int> _rosterSlotIndices = new List<int>();
        private bool _rosterRefreshing;

        // ---- ActivePlayerContext: single active player source for ALL write actions ----
        // Only updated after a successful read (either source). All writes use _apAddress
        // via the roster args passed to the backend (fail-closed re-resolution each write).
        private string _apSource;      // "SelectedPlayer" | "RosterBrowser"
        private string _apAddress;     // verified player address ("0x...")
        private string _apName;
        private string _apFaceId;
        private string _apTeamName;
        private int _apTeamIndex = -1;
        private int _apPlayerIndex = -1;

        private bool _busy;
        private bool _backendReady;
        private bool _baselineReady;
        private readonly string _root;
        private readonly string _powershell;
        private readonly string _toolScript;
        private readonly string _myCareerToolScript;
        private readonly string _hiddenOptionsToolScript;
        private readonly string _parkMetaToolScript;

        private System.Windows.Forms.Timer _pollTimer;
        private ToolTip _tooltip;
        private int _lastPid;
        private bool _gameShaOk;
        private int _pollTick;
        private string _mcStatus = "OFF";
        private string _hoStatus = "OFF";

        private static readonly string[] WRITE_ACTIONS =
        { "attributes99", "attributes110", "restore-abilities", "max-badges", "restore-badges", "park-meta-apply", "park-meta-curry", "park-meta-lebron", "park-meta-kd", "park-meta-restore" };

        private static bool IsWriteAction(string a)
        {
            foreach (var w in WRITE_ACTIONS) if (a == w) return true;
            return false;
        }

        public MainForm()
        {
            _root = LocateProjectRoot();
            _powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            _toolScript = Path.Combine(_root, "Player-Tool.ps1");
            _myCareerToolScript = Path.Combine(_root, "MyCareer-Tool.ps1");
            _hiddenOptionsToolScript = Path.Combine(_root, "HiddenOptions-Tool.ps1");
            _parkMetaToolScript = Path.Combine(_root, "Park-Meta-Tool.ps1");

            BuildUi();
            SetBusy(false, null);
            Log("GUI 已啟動");
            Log("專案根目錄：" + _root);
            if (_backendReady)
            {
                Log("Player-Tool.ps1：已找到");
                Log("後端：READY");
            }
            else
            {
                Log("Player-Tool.ps1：找不到");
                LogWarning("後端：NOT FOUND");
                SetBackendUnavailable();
            }
            StartPolling();
        }

        /// <summary>Walk up from the executable directory looking for the project root markers.</summary>
        private string LocateProjectRoot()
        {
            string dir = Path.GetDirectoryName(Path.GetFullPath(Application.ExecutablePath));
            while (!string.IsNullOrEmpty(dir))
            {
                if (File.Exists(Path.Combine(dir, "Player-Tool.ps1")) &&
                    File.Exists(Path.Combine(dir, "PROJECT_STATUS.md")) &&
                    File.Exists(Path.Combine(dir, "src", "player_tool.py")))
                {
                    _backendReady = true;
                    return dir;
                }
                var parent = Directory.GetParent(dir);
                dir = parent != null ? parent.FullName : null;
            }
            _backendReady = false;
            return AppDomain.CurrentDomain.BaseDirectory;
        }

        private void SetBackendUnavailable()
        {
            foreach (var b in _actionButtons)
            {
                var action = (string)b.Tag;
                if (action != "read" && action != "dump")
                    b.Enabled = false;
            }
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (_backendReady)
                RunStartupMaintenanceAsync();
        }

        private async void RunStartupMaintenanceAsync()
        {
            try
            {
                Log("正在執行輕量日誌整理（保留永久資料 / baseline / 最近 session）...");
                var cleaned = await RunBackendActionAsync("retention-auto");
                LogInfo(">>> 輕量整理完成：" + SummarizeStatus(cleaned));
                await RefreshStatsAsync();
            }
            catch (Exception ex)
            {
                LogWarning("日誌整理失敗（不影響使用）: " + ex.Message);
            }
        }

        private string SummarizeStatus(BackendResult r)
        {
            if (r.ExitCode != 0) return "失敗";
            var m = Regex.Match(r.Stdout, "\"removed_read_files\"\\s*:\\s*(\\d+)");
            var s = Regex.Match(r.Stdout, "\"removed_sessions\"\\s*:\\s*(\\d+)");
            string rf = m.Success ? m.Groups[1].Value : "?";
            string rs = s.Success ? s.Groups[1].Value : "?";
            return "移除 read 暫存 " + rf + " 個、舊 session " + rs + " 個";
        }

        #region UI construction

        private void BuildUi()
        {
            Text = "NBA 2K21 離線修改器 Player Tool";
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = C_BG;
            ForeColor = C_TEXT;
            Font = new Font("Segoe UI", 9F);
            MinimumSize = new Size(780, 760);
            Size = new Size(880, 880);
            FormBorderStyle = FormBorderStyle.Sizable;
            AutoScaleMode = AutoScaleMode.Dpi;

            var body = new Panel { Dock = DockStyle.Fill, BackColor = C_BG, Padding = new Padding(14) };
            Controls.Add(body);

            var layout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                BackColor = C_BG,
                ColumnCount = 1,
                RowCount = 8,
                Padding = new Padding(0),
            };
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // title
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // connection
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // player info
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // player buttons
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // offline features
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100F)); // log
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // log mgmt
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // safety
            body.Controls.Add(layout);

            layout.Controls.Add(BuildHeader(), 0, 0);
            layout.Controls.Add(BuildConnectionBox(), 0, 1);
            layout.Controls.Add(BuildPlayerBox(), 0, 2);
            layout.Controls.Add(BuildActionBox(), 0, 3);
            layout.Controls.Add(BuildOfflineBox(), 0, 4);
            layout.Controls.Add(BuildLogBox(), 0, 5);
            layout.Controls.Add(BuildLogMgmtBox(), 0, 6);
            layout.Controls.Add(BuildSafetyBox(), 0, 7);
        }

        private Control BuildHeader()
        {
            var panel = new Panel { Dock = DockStyle.Fill, BackColor = C_BG, Height = 46, Margin = new Padding(0, 0, 0, 10) };
            var title = new Label
            {
                Text = "NBA 2K21 離線修改器",
                Dock = DockStyle.Top,
                Height = 30,
                BackColor = C_BG,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 15F, FontStyle.Bold),
                TextAlign = ContentAlignment.MiddleLeft,
            };
            var sub = new Label
            {
                Text = "V2F.L.SEngine · NBA 2K21 離線功能與球員修改工具 · 前端包裝層",
                Dock = DockStyle.Bottom,
                Height = 16,
                BackColor = C_BG,
                ForeColor = C_TEXT_DIM,
                Font = new Font("Segoe UI", 8.5F),
            };
            panel.Controls.Add(title);
            panel.Controls.Add(sub);
            return panel;
        }

        private Control BuildConnectionBox()
        {
            var box = MakeGroupBox("A. 連線 / 版本狀態");
            var t = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 2, RowCount = 4, Margin = new Padding(10) };
            t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 130));
            t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));

            _lblConnGame = MakeReadoutRow(t, 0, "遊戲連線");
            _lblConnSha = MakeReadoutRow(t, 1, "遊戲 SHA 驗證");
            _lblConnProc = MakeReadoutRow(t, 2, "進程識別");
            _lblConnTime = MakeReadoutRow(t, 3, "最後檢查時間");

            SetReadout(_lblConnGame, "未連線", C_BAD);
            SetReadout(_lblConnSha, "未驗證", C_TEXT_DIM);
            SetReadout(_lblConnProc, "—", C_TEXT_DIM);
            SetReadout(_lblConnTime, "—", C_TEXT_DIM);

            box.Controls.Add(t);
            return box;
        }

        private Control BuildPlayerBox()
        {
            var box = MakeGroupBox("B. 目前球員資訊");
            // 5 rows (姓名/Face ID/球隊槽位/來源/Baseline): explicit height so the added
            // 來源 row is never clipped by the GroupBox boundary at any DPI scale.
            box.Height = 162;
            box.MinimumSize = new Size(0, 162);
            var t = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 2, RowCount = 5, Margin = new Padding(10) };
            t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 150));
            t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));

            _lblName = MakeReadoutRow(t, 0, "姓名");
            _lblFace = MakeReadoutRow(t, 1, "Face ID");
            _lblTeam = MakeReadoutRow(t, 2, "球隊 / 槽位");
            _lblSource = MakeReadoutRow(t, 3, "來源");
            _lblBaseline = MakeReadoutRow(t, 4, "Baseline");

            SetReadout(_lblName, "—", C_TEXT_DIM);
            SetReadout(_lblFace, "—", C_TEXT_DIM);
            SetReadout(_lblTeam, "—", C_TEXT_DIM);
            SetReadout(_lblSource, "—", C_TEXT_DIM);
            SetReadout(_lblBaseline, "NOT READY", C_BAD);

            box.Controls.Add(t);
            return box;
        }

        private Control BuildActionBox()
        {
            var box = MakeGroupBox("C. 球員修改");
            // Two explicit rows (action buttons + roster browser): explicit height so the
            // second row (label / ComboBoxes / button) is fully visible, never clipped.
            box.Height = 170;
            box.MinimumSize = new Size(0, 170);
            var t = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 1, RowCount = 2, Margin = new Padding(10) };
            t.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            t.RowStyles.Add(new RowStyle(SizeType.AutoSize));

            var flow = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                WrapContents = true,
                AutoSize = true,
            };

            string[] labels = { "讀取目前球員", "保存快照 (Dump)", "全能力 99", "全能力 110", "恢復原能力", "全徽章", "恢復原徽章", "套用 2K21 PARK META", "Curry 動作包", "LeBron 動作包", "KD 動作包", "恢復原動作", "設定 MC 姓名：Roxy Migurdia" };
            string[] actions = { "read", "dump", "attributes99", "attributes110", "restore-abilities", "max-badges", "restore-badges", "park-meta-apply", "park-meta-curry", "park-meta-lebron", "park-meta-kd", "park-meta-restore", "park-meta-migrate-name" };

            var buttons = new List<Button>();
            for (int i = 0; i < actions.Length; i++)
            {
                bool primary = actions[i] == "attributes110" || actions[i] == "max-badges" || actions[i] == "park-meta-apply";
                var b = MakeButton(labels[i], actions[i], primary);
                flow.Controls.Add(b);
                buttons.Add(b);
            }
            _actionButtons = buttons.ToArray();
            t.Controls.Add(flow, 0, 0);

            // Roster 瀏覽 row (mode-agnostic player source: MyCAREER / MyLEAGUE)
            var roster = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                WrapContents = false,
                AutoSize = true,
            };
            var rosterLbl = new Label
            {
                Text = "Roster 瀏覽：",
                AutoSize = true,
                BackColor = C_PANEL,
                ForeColor = C_TEXT,
                Font = new Font("Segoe UI", 9F),
                TextAlign = ContentAlignment.MiddleLeft,
                Margin = new Padding(5, 12, 2, 5),
            };
            _cmbRosterTeam = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Width = 160,
                FlatStyle = FlatStyle.Flat,
                BackColor = C_BTN,
                ForeColor = C_TEXT,
                Margin = new Padding(5),
            };
            _cmbRosterTeam.SelectedIndexChanged += CmbRosterTeam_SelectedIndexChanged;
            _cmbRosterPlayer = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Width = 210,
                FlatStyle = FlatStyle.Flat,
                BackColor = C_BTN,
                ForeColor = C_TEXT,
                Margin = new Padding(5),
            };
            _btnRosterRead = MakeButton("讀取此球員", "roster-read", false);
            _btnRosterRead.Click -= ActionButton_Click;
            _btnRosterRead.Click += RosterReadButton_Click;
            roster.Controls.Add(rosterLbl);
            roster.Controls.Add(_cmbRosterTeam);
            roster.Controls.Add(_cmbRosterPlayer);
            roster.Controls.Add(_btnRosterRead);
            t.Controls.Add(roster, 0, 1);

            box.Controls.Add(t);
            return box;
        }

        private Control BuildOfflineBox()
        {
            var box = MakeGroupBox("D. 離線功能");
            box.Height = 104;
            box.MinimumSize = new Size(0, 104);
            var t = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 2, RowCount = 2, Margin = new Padding(10) };
            t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 340));
            t.RowStyles.Add(new RowStyle(SizeType.Percent, 50F));
            t.RowStyles.Add(new RowStyle(SizeType.Percent, 50F));

            // Row 0: Offline MyCAREER
            var mc = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 2, RowCount = 1 };
            mc.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            mc.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            var mcLbl = new Label { Text = "離線 MyCAREER：", Dock = DockStyle.Fill, BackColor = C_PANEL, ForeColor = C_TEXT, TextAlign = ContentAlignment.MiddleLeft, AutoSize = false };
            _lblMc = new Label { Text = "—", Dock = DockStyle.Fill, BackColor = C_PANEL, ForeColor = C_TEXT_DIM, TextAlign = ContentAlignment.MiddleLeft, AutoSize = false };
            mc.Controls.Add(mcLbl, 0, 0);
            mc.Controls.Add(_lblMc, 1, 0);
            t.Controls.Add(mc, 0, 0);

            _btnMcEnable = MakeButton("啟用離線 MyCAREER", "mc-enable", true);
            _btnMcDisable = MakeButton("停用離線 MyCAREER", "mc-disable", false);
            _btnMcEnable.Click -= ActionButton_Click; _btnMcEnable.Click += OfflineButton_Click;
            _btnMcDisable.Click -= ActionButton_Click; _btnMcDisable.Click += OfflineButton_Click;
            _tooltip = new ToolTip();
            _tooltip.SetToolTip(_btnMcDisable, "停用離線 MyCAREER；若部分 Patch 已套用（需要修復），會恢復所有可確認的 Patch。");
            var mcFlow = new FlowLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, WrapContents = false };
            mcFlow.Controls.Add(_btnMcEnable);
            mcFlow.Controls.Add(_btnMcDisable);
            t.Controls.Add(mcFlow, 1, 0);

            // Row 1: Hidden Options
            var ho = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 2, RowCount = 1 };
            ho.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            ho.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            var hoLbl = new Label { Text = "隱藏選項：", Dock = DockStyle.Fill, BackColor = C_PANEL, ForeColor = C_TEXT, TextAlign = ContentAlignment.MiddleLeft, AutoSize = false };
            _lblHo = new Label { Text = "—", Dock = DockStyle.Fill, BackColor = C_PANEL, ForeColor = C_TEXT_DIM, TextAlign = ContentAlignment.MiddleLeft, AutoSize = false };
            ho.Controls.Add(hoLbl, 0, 0);
            ho.Controls.Add(_lblHo, 1, 0);
            t.Controls.Add(ho, 0, 1);

            _btnHoEnable = MakeButton("解鎖隱藏選項", "ho-enable", true);
            _btnHoDisable = MakeButton("恢復隱藏選項", "ho-disable", false);
            _btnHoEnable.Click -= ActionButton_Click; _btnHoEnable.Click += OfflineButton_Click;
            _btnHoDisable.Click -= ActionButton_Click; _btnHoDisable.Click += OfflineButton_Click;
            var hoFlow = new FlowLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, WrapContents = false };
            hoFlow.Controls.Add(_btnHoEnable);
            hoFlow.Controls.Add(_btnHoDisable);
            t.Controls.Add(hoFlow, 1, 1);

            box.Controls.Add(t);
            return box;
        }

        private Control BuildLogBox()
        {
            var box = MakeGroupBox("E. 輸出 / 日誌");
            box.Padding = new Padding(10);
            _log = new RichTextBox
            {
                Dock = DockStyle.Fill,
                Multiline = true,
                ReadOnly = true,
                ScrollBars = RichTextBoxScrollBars.Vertical,
                WordWrap = false,
                BackColor = Color.FromArgb(24, 24, 24),
                ForeColor = C_TEXT,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Consolas", 9F),
            };
            box.Controls.Add(_log);
            return box;
        }

        private Control BuildLogMgmtBox()
        {
            var box = MakeGroupBox("F. 日誌管理");
            var top = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, ColumnCount = 2, RowCount = 2, Margin = new Padding(10) };
            top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 320));

            _lblStats = new Label
            {
                Text = "日誌大小：計算中…",
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                ForeColor = C_TEXT,
                Font = new Font("Segoe UI", 8.5F),
                TextAlign = ContentAlignment.MiddleLeft,
            };
            top.Controls.Add(_lblStats, 0, 0);
            top.SetColumnSpan(_lblStats, 2);

            var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, BackColor = C_PANEL, Padding = new Padding(0, 4, 0, 0), WrapContents = false };
            var clean = MakeButton("清理舊日誌", "retention-purge", false);
            clean.Click -= ActionButton_Click; clean.Click += LogMgmtButton_Click;
            var open = MakeButton("開啟日誌資料夾", "open-logs", false);
            open.Click -= ActionButton_Click; open.Click += LogMgmtButton_Click;
            _chkDebug = new CheckBox
            {
                Text = "Debug 模式（保存完整 before/after/diff）",
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                ForeColor = C_TEXT_DIM,
                Font = new Font("Segoe UI", 8.5F),
                TextAlign = ContentAlignment.MiddleLeft,
                AutoSize = false,
            };
            flow.Controls.Add(clean);
            flow.Controls.Add(open);
            flow.Controls.Add(_chkDebug);
            top.Controls.Add(flow, 1, 1);

            box.Controls.Add(top);
            return box;
        }

        private Control BuildSafetyBox()
        {
            var box = MakeGroupBox("G. 安全提示");
            var label = new Label
            {
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                ForeColor = C_WARN,
                Font = new Font("Segoe UI", 8.5F),
                Padding = new Padding(10, 6, 10, 6),
                Text =
                    "• 本工具僅適用離線模式，不會修改原始 EXE；所有修改皆為 runtime patch，不永久修改 NBA2K21.exe。\r\n" +
                    "• 所有寫入都受 SHA / baseline / journal / selected-player 身分校驗保護，來源不符即停止。\r\n" +
                    "• Offline MyCAREER 與隱藏選項在遊戲重新啟動後需重新啟用；建議在主選單停用 Offline MyCAREER。\r\n" +
                    "• 隱藏選項含 DEBUG REPLAY / ANIM DEBUG / STORY DEBUG 等遊戲內隱藏功能，非所有項目都保證適合日常使用。\r\n" +
                    "• 若重啟遊戲或更換存檔 / 隊伍，位置會改變，舊 session 會被拒絕，需重新「讀取目前球員」。\r\n" +
                    "• 全能力110 與 全徽章 會寫入記憶體；建議先備份 / 確認離線存檔可還原。",
            };
            box.Controls.Add(label);
            return box;
        }

        private GroupBox MakeGroupBox(string text)
        {
            var g = new GroupBox
            {
                Text = text,
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                ForeColor = C_ACCENT,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                Padding = new Padding(8, 4, 8, 8),
                Margin = new Padding(0, 0, 0, 10),
            };
            return g;
        }

        private static Label MakeReadoutRow(TableLayoutPanel t, int row, string key)
        {
            var pair = MakeKeyValue(t, row, key);
            return pair.Item2;
        }

        private static Tuple<Label, Label> MakeKeyValue(TableLayoutPanel t, int row, string key)
        {
            var k = new Label
            {
                Text = key,
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                ForeColor = C_TEXT_DIM,
                Font = new Font("Segoe UI", 9F),
                TextAlign = ContentAlignment.MiddleLeft,
                Padding = new Padding(4, 2, 0, 2),
            };
            var v = new Label
            {
                Text = "—",
                Dock = DockStyle.Fill,
                BackColor = C_PANEL,
                ForeColor = C_TEXT,
                Font = new Font("Segoe UI", 9F),
                TextAlign = ContentAlignment.MiddleLeft,
                Padding = new Padding(4, 2, 0, 2),
                AutoEllipsis = true,
            };
            t.Controls.Add(k, 0, row);
            t.Controls.Add(v, 1, row);
            return Tuple.Create(k, v);
        }

        private Button MakeButton(string text, string action, bool primary)
        {
            var b = new Button
            {
                Text = text,
                Tag = action,
                Width = 150,
                Height = 38,
                Margin = new Padding(5),
                FlatStyle = FlatStyle.Flat,
                BackColor = C_BTN,
                ForeColor = primary ? C_ACCENT : C_TEXT,
                Font = new Font("Segoe UI", 9.5F, primary ? FontStyle.Bold : FontStyle.Regular),
                Cursor = Cursors.Hand,
            };
            b.FlatAppearance.BorderColor = primary ? C_ACCENT : C_BTN_BORDER;
            b.FlatAppearance.MouseOverBackColor = C_BTN_HOVER;
            b.FlatAppearance.MouseDownBackColor = Color.FromArgb(45, 45, 48);
            b.Click += ActionButton_Click;
            return b;
        }

        private static void SetReadout(Label l, string text, Color color)
        {
            l.Text = text;
            l.ForeColor = color;
        }

        #endregion

        #region Actions

        private async void ActionButton_Click(object sender, EventArgs e)
        {
            var btn = (Button)sender;
            var action = (string)btn.Tag;
            if (_busy)
            {
                LogWarning("已有操作在執行，請稍候。");
                return;
            }
            bool debug = IsWriteAction(action) && _chkDebug != null && _chkDebug.Checked;
            SetBusy(true, btn);
            try
            {
                var result = await RunBackendActionAsync(action, debug);
                HandleResult(action, result);
            }
            catch (Exception ex)
            {
                LogError("未預期錯誤: " + ex.Message);
            }
            finally
            {
                SetBusy(false, btn);
            }
        }

        private async void LogMgmtButton_Click(object sender, EventArgs e)
        {
            var btn = (Button)sender;
            var action = (string)btn.Tag;
            if (_busy)
            {
                LogWarning("已有操作在執行，請稍候。");
                return;
            }
            if (action == "open-logs")
            {
                try { Process.Start("explorer.exe", Path.Combine(_root, "logs")); }
                catch (Exception ex) { LogError("無法開啟資料夾: " + ex.Message); }
                return;
            }
            if (action == "retention-purge")
            {
                var res = MessageBox.Show(
                    "確定要執行較完整的舊日誌清理？\n\n會保留：永久研究資料、有效 per-player baseline、最近交易與 session。\n只移除超出保留原則的舊 session 與 read 暫存。",
                    "清理舊日誌", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (res != DialogResult.Yes) return;
                SetBusy(true, btn);
                try
                {
                    var r = await RunBackendActionAsync("retention-purge");
                    Log("");
                    if (!string.IsNullOrWhiteSpace(r.Stdout)) Log(r.Stdout.TrimEnd());
                    LogInfo(">>> 清理完成：" + SummarizeStatus(r));
                    await RefreshStatsAsync();
                }
                catch (Exception ex) { LogError("清理失敗: " + ex.Message); }
                finally { SetBusy(false, btn); }
            }
        }

        private void SetBusy(bool busy, Button origin)
        {
            _busy = busy;
            foreach (var b in _actionButtons)
            {
                var a = (string)b.Tag;
                if (a.StartsWith("park-meta-"))
                    b.Enabled = _backendReady && !busy;
                else if (a == "read" || a == "dump")
                    b.Enabled = !busy || b == origin;
                else
                    b.Enabled = _baselineReady && (!busy || b == origin);
            }
            UpdateGating();
        }

        private Task<BackendResult> RunBackendActionAsync(string action, bool debug = false)
        {
            Log(">>> 執行後端操作: " + ActionLabel(action));
            return Task.Run(() => RunProcess(action, debug));
        }

        private BackendResult RunProcess(string action, bool debug)
        {
            // PARK META actions run through Park-Meta-Tool.ps1 (own fail-closed backup/restore).
            if (action.StartsWith("park-meta-"))
            {
                string parkAction = action.Substring("park-meta-".Length);
                string psiArgs = string.Format(
                    "-NoProfile -ExecutionPolicy Bypass -File \"{0}\" -Action {1}",
                    _parkMetaToolScript, (parkAction == "curry" || parkAction == "lebron" || parkAction == "kd") ? "apply" : parkAction);
                if (parkAction == "curry" || parkAction == "lebron" || parkAction == "kd")
                    psiArgs += " -JumpShot " + parkAction;
                var psiPark = new ProcessStartInfo
                {
                    FileName = _powershell,
                    Arguments = psiArgs,
                    WorkingDirectory = _root,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                };
                using (var p = Process.Start(psiPark))
                {
                    string stdout = p.StandardOutput.ReadToEnd();
                    string stderr = p.StandardError.ReadToEnd();
                    p.WaitForExit();
                    return new BackendResult(action, p.ExitCode, stdout, stderr);
                }
            }
            string args = string.Format(
                "-NoProfile -ExecutionPolicy Bypass -File \"{0}\" -Action {1}",
                _toolScript, action);
            if (debug) args += " -DebugMode";
            // All actions except the legacy "read" (game selection) and retention follow the
            // ActivePlayerContext: when the source is RosterBrowser, pass the roster indices so
            // the backend re-resolves the same roster pick fail-closed on every operation.
            if (action != "read" && !action.StartsWith("retention-"))
            {
                int[] ra = RosterArgsForContext();
                if (ra != null) args += string.Format(" -RosterTeam {0} -RosterPlayer {1}", ra[0], ra[1]);
            }
            var psi = new ProcessStartInfo
            {
                FileName = _powershell,
                Arguments = args,
                WorkingDirectory = _root,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };

            using (var p = Process.Start(psi))
            {
                string stdout = p.StandardOutput.ReadToEnd();
                string stderr = p.StandardError.ReadToEnd();
                p.WaitForExit();
                return new BackendResult(action, p.ExitCode, stdout, stderr);
            }
        }

        private BackendResult RunScriptAction(string script, string action)
        {
            var psi = new ProcessStartInfo
            {
                FileName = _powershell,
                Arguments = string.Format("-NoProfile -ExecutionPolicy Bypass -File \"{0}\" -Action {1}",
                    script, action),
                WorkingDirectory = _root,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            using (var p = Process.Start(psi))
            {
                string stdout = p.StandardOutput.ReadToEnd();
                string stderr = p.StandardError.ReadToEnd();
                p.WaitForExit();
                return new BackendResult(action, p.ExitCode, stdout, stderr);
            }
        }

        #region Roster browser (mode-agnostic player source)

        private int[] RosterArgsForContext()
        {
            // Roster args for every write action; null when the active source is SelectedPlayer.
            if (_apSource != "RosterBrowser") return null;
            if (_apTeamIndex < 0 || _apPlayerIndex < 0) return null;
            return new[] { _apTeamIndex, _apPlayerIndex };
        }

        private void SetActiveContext(string source, string addr, string name, string face,
            string teamIndex, string slot, string teamName)
        {
            _apSource = source; _apAddress = addr; _apName = name; _apFaceId = face;
            _apTeamName = teamName;
            int ti; int pi;
            _apTeamIndex = int.TryParse(teamIndex, out ti) ? ti : -1;
            _apPlayerIndex = int.TryParse(slot, out pi) ? pi : -1;
            SetReadout(_lblSource, source == "RosterBrowser" ? "Roster 瀏覽" : "目前選中球員", C_ACCENT);
            UpdateGating();
        }

        private void ClearActiveContext()
        {
            _apSource = null; _apAddress = null; _apName = null; _apFaceId = null;
            _apTeamName = null; _apTeamIndex = -1; _apPlayerIndex = -1;
            _baselineReady = false;
            SetReadout(_lblName, "—", C_TEXT_DIM);
            SetReadout(_lblFace, "—", C_TEXT_DIM);
            SetReadout(_lblTeam, "—", C_TEXT_DIM);
            SetReadout(_lblSource, "—", C_TEXT_DIM);
            SetReadout(_lblBaseline, "NOT READY", C_BAD);
            UpdateGating();
        }

        private void ClearRosterCache()
        {
            _rosterTeamIndices.Clear();
            _rosterSlotIndices.Clear();
            if (_cmbRosterTeam != null) { _cmbRosterTeam.Items.Clear(); _cmbRosterTeam.SelectedIndex = -1; }
            if (_cmbRosterPlayer != null) { _cmbRosterPlayer.Items.Clear(); _cmbRosterPlayer.SelectedIndex = -1; }
        }

        /// <summary>Load the roster team list into the team ComboBox (backend: roster-teams).</summary>
        private async Task RefreshRosterTeamsAsync()
        {
            if (_busy || _rosterRefreshing) return;
            if (_lastPid == 0 || !_gameShaOk) return;
            _rosterRefreshing = true;
            try
            {
                Log(">>> Roster 瀏覽：載入球隊清單…");
                var r = await Task.Run(() => RunProcess("roster-teams", false));
                if (r.ExitCode != 0)
                {
                    LogWarning(">>> Roster 球隊載入失敗（退出碼 " + r.ExitCode + "）。");
                    ClearRosterCache();
                    return;
                }
                var json = SimpleJson.Parse(r.Stdout);
                var teams = json.GetArray("teams");
                if (teams == null || teams.Count == 0)
                {
                    LogWarning(">>> Roster 表為空或無法讀取。");
                    ClearRosterCache();
                    return;
                }
                _rosterTeamIndices.Clear();
                _cmbRosterTeam.Items.Clear();
                int unreadable = 0;
                foreach (var tm in teams)
                {
                    string idxStr = tm.Get("team_index");
                    string name = tm.Get("team_name");
                    int idx;
                    if (!int.TryParse(idxStr, out idx)) continue;
                    if (string.IsNullOrEmpty(name)) { unreadable++; continue; }
                    _rosterTeamIndices.Add(idx);
                    _cmbRosterTeam.Items.Add(idx + ". " + name);
                }
                LogInfo(">>> Roster 球隊清單就緒：" + _rosterTeamIndices.Count + " 隊"
                    + (unreadable > 0 ? "（另 " + unreadable + " 隊名稱不可讀，已略過）" : "") + "。");
                _rosterSlotIndices.Clear();
                if (_cmbRosterPlayer != null) { _cmbRosterPlayer.Items.Clear(); _cmbRosterPlayer.SelectedIndex = -1; }
            }
            catch (Exception ex)
            {
                LogWarning("Roster 球隊載入失敗: " + ex.Message);
                ClearRosterCache();
            }
            finally
            {
                _rosterRefreshing = false;
            }
        }

        private void CmbRosterTeam_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (_busy || _rosterRefreshing) return;
            if (_cmbRosterTeam == null || _cmbRosterTeam.SelectedIndex < 0) return;
            if (_cmbRosterTeam.SelectedIndex >= _rosterTeamIndices.Count) return;
            int teamIndex = _rosterTeamIndices[_cmbRosterTeam.SelectedIndex];
            if (_lastPid == 0 || !_gameShaOk) return;
            _rosterRefreshing = true;
            try
            {
                Log(">>> Roster 瀏覽：載入球隊 " + teamIndex + " 的球員清單…");
                string args = string.Format(
                    "-NoProfile -ExecutionPolicy Bypass -File \"{0}\" -Action roster-players -RosterTeam {1}",
                    _toolScript, teamIndex);
                string stdout, stderr; int exit;
                using (var p = Process.Start(new ProcessStartInfo
                {
                    FileName = _powershell,
                    Arguments = args,
                    WorkingDirectory = _root,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                }))
                {
                    stdout = p.StandardOutput.ReadToEnd();
                    stderr = p.StandardError.ReadToEnd();
                    p.WaitForExit();
                    exit = p.ExitCode;
                }
                if (exit != 0)
                {
                    LogWarning(">>> Roster 球員載入失敗：" + LastLine(stdout));
                    _rosterSlotIndices.Clear();
                    _cmbRosterPlayer.Items.Clear();
                    return;
                }
                var json = SimpleJson.Parse(stdout);
                var players = json.GetArray("players");
                _rosterSlotIndices.Clear();
                _cmbRosterPlayer.Items.Clear();
                if (players != null)
                {
                    foreach (var pl in players)
                    {
                        string slotStr = pl.Get("slot");
                        string addr = pl.Get("player_address");
                        int slot;
                        if (!int.TryParse(slotStr, out slot)) continue;
                        if (string.IsNullOrEmpty(addr) || addr == null) continue;
                        string valid = pl.GetStr("valid");
                        string given = pl.Get("given_name");
                        string surname = pl.Get("surname");
                        string face = pl.Get("face_id");
                        if (valid != "true" || string.IsNullOrEmpty(given)) continue;
                        _rosterSlotIndices.Add(slot);
                        _cmbRosterPlayer.Items.Add("slot " + slot + ": " + given + " " + surname + "  (face " + face + ")");
                    }
                }
                LogInfo(">>> Roster 球員清單就緒：" + _rosterSlotIndices.Count + " 位有效球員。");
            }
            catch (Exception ex)
            {
                LogWarning("Roster 球員載入失敗: " + ex.Message);
            }
            finally
            {
                _rosterRefreshing = false;
                UpdateGating();
            }
        }

        private async void RosterReadButton_Click(object sender, EventArgs e)
        {
            if (_busy) { LogWarning("已有操作在執行，請稍候。"); return; }
            if (_cmbRosterTeam == null || _cmbRosterTeam.SelectedIndex < 0 ||
                _cmbRosterPlayer == null || _cmbRosterPlayer.SelectedIndex < 0)
            {
                LogWarning("請先選擇球隊與球員。");
                return;
            }
            if (_cmbRosterTeam.SelectedIndex >= _rosterTeamIndices.Count ||
                _cmbRosterPlayer.SelectedIndex >= _rosterSlotIndices.Count)
            {
                LogWarning("Roster 選取已失效，請重新選擇。");
                return;
            }
            int teamIndex = _rosterTeamIndices[_cmbRosterTeam.SelectedIndex];
            int slotIndex = _rosterSlotIndices[_cmbRosterPlayer.SelectedIndex];
            SetBusy(true, _btnRosterRead);
            try
            {
                string args = string.Format(
                    "-NoProfile -ExecutionPolicy Bypass -File \"{0}\" -Action read -RosterTeam {1} -RosterPlayer {2}",
                    _toolScript, teamIndex, slotIndex);
                var result = await Task.Run(() =>
                {
                    using (var p = Process.Start(new ProcessStartInfo
                    {
                        FileName = _powershell,
                        Arguments = args,
                        WorkingDirectory = _root,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        StandardOutputEncoding = Encoding.UTF8,
                        StandardErrorEncoding = Encoding.UTF8,
                    }))
                    {
                        string stdout = p.StandardOutput.ReadToEnd();
                        string stderr = p.StandardError.ReadToEnd();
                        p.WaitForExit();
                        return new BackendResult("read", p.ExitCode, stdout, stderr);
                    }
                });
                HandleResult("read", result, "RosterBrowser");
            }
            catch (Exception ex)
            {
                LogError("未預期錯誤: " + ex.Message);
            }
            finally
            {
                SetBusy(false, _btnRosterRead);
            }
        }

        #endregion

        #region Offline features + polling

        private void StartPolling()
        {
            _pollTimer = new System.Windows.Forms.Timer { Interval = 2500 };
            _pollTimer.Tick += async (s, e) => { try { await PollTickAsync(); } catch (Exception) { } };
            _pollTimer.Start();
        }

        private static int GetGamePid()
        {
            try
            {
                var ps = Process.GetProcessesByName("NBA2K21");
                return ps.Length > 0 ? ps[0].Id : 0;
            }
            catch { return 0; }
        }

        private async Task PollTickAsync()
        {
            int pid = GetGamePid();
            bool present = pid != 0;
            bool changed = present != (_lastPid != 0) || (present && pid != _lastPid);
            _lastPid = pid;
            SetReadout(_lblConnGame, present ? "已連線" : "未連線", present ? C_OK : C_BAD);
            SetReadout(_lblConnProc, present ? ("PID " + pid) : "—", present ? C_TEXT : C_TEXT_DIM);
            SetReadout(_lblConnTime, DateTime.Now.ToString("HH:mm:ss"), C_TEXT_DIM);
            if (changed)
            {
                // Never reuse a player address / roster cache across a game restart or exit.
                ClearActiveContext();
                ClearRosterCache();
                if (present) { await VerifyGameShaAsync(); }
                else { _gameShaOk = false; SetReadout(_lblConnSha, "未驗證", C_TEXT_DIM); _mcStatus = "OFF"; _hoStatus = "OFF"; }
                await RefreshFeatureStatusAsync();
                if (present && _gameShaOk) { await RefreshRosterTeamsAsync(); }
            }
            else if (present)
            {
                _pollTick++;
                if (_pollTick % 2 == 0) await RefreshFeatureStatusAsync();
            }
            UpdateGating();
        }

        private async Task VerifyGameShaAsync()
        {
            try
            {
                string path = null;
                try { var ps = Process.GetProcessesByName("NBA2K21"); if (ps.Length > 0) path = ps[0].MainModule.FileName; } catch { }
                if (string.IsNullOrEmpty(path) || !File.Exists(path)) path = Path.Combine(@"E:\SteamLibrary\NBA2K21", "NBA2K21.exe");
                string sha = await Task.Run(() =>
                {
                    using (var fs = File.OpenRead(path))
                    using (var h = System.Security.Cryptography.SHA256.Create())
                        return BitConverter.ToString(h.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
                });
                bool ok = sha == "5dbd9408dff48f3d36f34748ae505aacb73a9935e9a9eafb7f345cb9c6325556";
                _gameShaOk = ok;
                SetReadout(_lblConnSha, ok ? "已驗證" : "版本不符", ok ? C_OK : C_BAD);
                if (!ok) LogError(">>> 遊戲 SHA 驗證失敗，離線功能已停用。");
            }
            catch (Exception ex)
            {
                _gameShaOk = false;
                SetReadout(_lblConnSha, "偵測失敗", C_BAD);
                LogWarning("SHA 檢查失敗: " + ex.Message);
            }
        }

        private async Task RefreshFeatureStatusAsync()
        {
            if (_busy) return;
            try
            {
                var mc = await Task.Run(() => RunScriptAction(_myCareerToolScript, "offline-mycareer-status"));
                string mcSt = ParseField(mc.Stdout, "offline_mycareer") ?? "OFF";
                _mcStatus = ParseField(mc.Stdout, "status") == "STOPPED" ? "STOPPED" : mcSt;
                var ho = await Task.Run(() => RunScriptAction(_hiddenOptionsToolScript, "hidden-options-status"));
                string hoSt = ParseField(ho.Stdout, "hidden_options") ?? "OFF";
                _hoStatus = ParseField(ho.Stdout, "status") == "STOPPED" ? "STOPPED" : hoSt;
            }
            catch (Exception)
            {
                _mcStatus = "STOPPED"; _hoStatus = "STOPPED";
            }
            UpdateStatusLabels();
        }

        private void UpdateStatusLabels()
        {
            if (!(_lastPid != 0)) { SetReadout(_lblMc, "—", C_TEXT_DIM); SetReadout(_lblHo, "—", C_TEXT_DIM); return; }
            SetFeatureReadout(_lblMc, _mcStatus);
            SetFeatureReadout(_lblHo, _hoStatus);
        }

        private void SetFeatureReadout(Label l, string st)
        {
            switch (st)
            {
                case "ON": SetReadout(l, "已啟用", C_OK); break;
                case "OFF": SetReadout(l, "未啟用", C_TEXT_DIM); break;
                case "MIXED": SetReadout(l, "部分啟用（需要修復）", C_WARN); break;
                case "STOPPED": SetReadout(l, "偵測失敗", C_BAD); break;
                default: SetReadout(l, "—", C_TEXT_DIM); break;
            }
        }

        private void UpdateGating()
        {
            if (_btnMcEnable == null) return;
            bool gameOk = (_lastPid != 0) && _gameShaOk && !_busy;
            bool mcReady = gameOk && _mcStatus != "STOPPED";
            bool hoReady = gameOk && _hoStatus != "STOPPED";
            // Enable button only when OFF; disable/reset button when ON or MIXED.
            _btnMcEnable.Enabled = mcReady && _mcStatus == "OFF";
            _btnMcDisable.Enabled = gameOk && (_mcStatus == "ON" || _mcStatus == "MIXED");
            _btnHoEnable.Enabled = hoReady && _hoStatus == "OFF";
            _btnHoDisable.Enabled = gameOk && (_hoStatus == "ON" || _hoStatus == "MIXED");
            // Roster 瀏覽 read button: requires a live game, a verified SHA, and both picks.
            if (_btnRosterRead != null && _cmbRosterTeam != null && _cmbRosterPlayer != null)
                _btnRosterRead.Enabled = gameOk
                    && _cmbRosterTeam.SelectedIndex >= 0 && _cmbRosterTeam.SelectedIndex < _rosterTeamIndices.Count
                    && _cmbRosterPlayer.SelectedIndex >= 0 && _cmbRosterPlayer.SelectedIndex < _rosterSlotIndices.Count;
        }

        private async void OfflineButton_Click(object sender, EventArgs e)
        {
            var btn = (Button)sender;
            var tag = (string)btn.Tag;
            if (_busy) { LogWarning("已有操作在執行，請稍候。"); return; }
            if (tag == "mc-disable" && _mcStatus == "ON")
            {
                var res = MessageBox.Show(
                    "建議先返回 NBA 2K21 主選單後再停用離線 MyCAREER。\n是否繼續？",
                    "停用離線 MyCAREER", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (res != DialogResult.Yes) return;
            }
            string script, action;
            switch (tag)
            {
                case "mc-enable": script = _myCareerToolScript; action = "enable-offline-mycareer"; break;
                case "mc-disable": script = _myCareerToolScript; action = "disable-offline-mycareer"; break;
                case "ho-enable": script = _hiddenOptionsToolScript; action = "enable-hidden-options"; break;
                default: script = _hiddenOptionsToolScript; action = "disable-hidden-options"; break;
            }
            SetBusy(true, btn);
            try
            {
                Log(">>> " + ActionLabel(tag) + "…");
                var result = await Task.Run(() => RunScriptAction(script, action));
                HandleOfflineResult(tag, result);
                await RefreshFeatureStatusAsync();
            }
            catch (Exception ex) { LogError("未預期錯誤: " + ex.Message); }
            finally { SetBusy(false, btn); }
        }

        private void HandleOfflineResult(string tag, BackendResult r)
        {
            Log("");
            if (!string.IsNullOrWhiteSpace(r.Stdout)) Log(r.Stdout.TrimEnd());
            if (!string.IsNullOrWhiteSpace(r.Stderr)) LogError("STDERR:\r\n" + r.Stderr.TrimEnd());
            string status = ParseField(r.Stdout, "status");
            if (status == "STOPPED")
            {
                bool rolled = ParseField(r.Stdout, "rolled_back") == "true";
                string err = ParseField(r.Stdout, "error");
                if (rolled) LogError(">>> " + ActionLabel(tag) + " 失敗，前置 Patch 已自動恢復（未啟用）。");
                else LogError(">>> " + ActionLabel(tag) + " 失敗。");
                if (!string.IsNullOrEmpty(err)) LogError("   " + err);
                MessageBox.Show(ActionLabel(tag) + " 失敗。\n\n" + (string.IsNullOrEmpty(err) ? "請查看日誌區。" : err),
                    "操作失敗", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            if (r.ExitCode != 0)
            {
                LogError(">>> " + ActionLabel(tag) + " 失敗（退出碼 " + r.ExitCode + "）。請查看日誌。");
                MessageBox.Show(ActionLabel(tag) + " 失敗，請查看日誌區。", "操作失敗",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            if (status == "NOOP")
                LogInfo(">>> " + ActionLabel(tag) + "：已是目標狀態（NOOP）。");
            else if (status == "PATCHED" || status == "VERIFIED" || status == "RESTORED")
                LogInfo(">>> " + ActionLabel(tag) + " 完成。");
            else
                LogWarning(">>> " + ActionLabel(tag) + " 完成（退出碼 0）。");
        }

        #endregion

        private async Task RefreshStatsAsync()
        {
            try
            {
                var r = await RunBackendActionAsync("retention-summary");
                if (r.ExitCode != 0) return;
                long size = ParseLong(r.Stdout, "size_bytes");
                long tx = ParseLong(r.Stdout, "transactions");
                long oldS = ParseLong(r.Stdout, "old_sessions");
                long sess = ParseLong(r.Stdout, "sessions");
                if (size < 0 || tx < 0 || sess < 0) return;
                _lblStats.Text = string.Format(
                    "日誌大小：{0}    交易記錄：{1} 筆    舊 Session：{2} 個（共 {3}）",
                    HumanSize(size), tx, oldS, sess);
            }
            catch (Exception) { }
        }

        private void HandleResult(string action, BackendResult r, string readSource = null)
        {
            Log("");
            if (!string.IsNullOrWhiteSpace(r.Stdout))
                Log(r.Stdout.TrimEnd());
            if (!string.IsNullOrWhiteSpace(r.Stderr))
                LogError("STDERR:\r\n" + r.Stderr.TrimEnd());

            if (action.StartsWith("retention-")) return;

            if (r.ExitCode != 0)
            {
                _baselineReady = false;
                SetBusy(false, null);
                LogError(">>> 操作失敗（退出碼 " + r.ExitCode + "）。請查看上述輸出與 logs。");
                MessageBox.Show("操作失敗，請查看日誌區。\n\n" + LastLine(r.Stdout), "操作失敗",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            if (action == "read") { ApplyReadReport(r.Stdout, readSource ?? "SelectedPlayer"); return; }
            if (action == "dump") { MarkResult(action); return; }
            if (IsWriteAction(action)) { HandleWriteResult(action, r); return; }
        }

        private void HandleWriteResult(string action, BackendResult r)
        {
            string status = ParseField(r.Stdout, "status");
            SetReadout(_lblConnTime, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"), C_TEXT_DIM);
            if (status == "NOOP")
            {
                string msg = ParseField(r.Stdout, "message");
                if (string.IsNullOrEmpty(msg)) msg = "目前已是此狀態，無需操作。";
                LogInfo(">>> " + msg);
                MessageBox.Show(msg, "資訊", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            else
            {
                LogInfo(">>> 完成：" + ActionLabel(action));
                MessageBox.Show("操作完成：" + ActionLabel(action) + "。\n請查看日誌區與產物（sessions / analysis / logs）。",
                    "完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            RefreshStatsAsync();
        }

        private void ApplyReadReport(string stdout, string readSource)
        {
            // stdout 含 {"name":..., "report":"logs/read_cache/player_*.json", ...}
            var m = Regex.Match(stdout, "\"report\"\\s*:\\s*\"([^\"]+)\"");
            string reportPath = null;
            if (m.Success)
                reportPath = Path.Combine(_root, m.Groups[1].Value.Replace('/', Path.DirectorySeparatorChar));
            if (reportPath == null || !File.Exists(reportPath))
            {
                SetReadout(_lblName, "已讀取", C_OK);
                SetReadout(_lblConnGame, "已連線", C_OK);
                SetReadout(_lblBaseline, "NOT READY", C_BAD);
                _baselineReady = false;
                SetBusy(false, null);
                LogInfo(">>> 讀取完成，但無法定位完整報告檔。");
                return;
            }
            try
            {
                var json = SimpleJson.Parse(File.ReadAllText(reportPath, Encoding.UTF8));
                var name = json.Get("name") ?? "—";
                var face = json.Get("face_id") ?? "—";

                string team = "—", slot = "—";
                var mem = json.GetArray("membership");
                if (mem != null && mem.Count > 0)
                {
                    var m0 = mem[0];
                    team = (m0.Get("team_name") ?? "—") + "  (index " + (m0.Get("team_index") ?? "?") + ")";
                    slot = m0.Get("slot") ?? "—";
                }

                bool ready = false;
                var baseline = json.GetChild("baseline");
                if (baseline != null)
                    ready = baseline.GetStr("status") == "READY";

                SetReadout(_lblName, name, C_OK);
                SetReadout(_lblFace, face, C_TEXT);
                SetReadout(_lblTeam, team + "  ·  槽位 slot " + slot, C_TEXT);
                SetReadout(_lblConnGame, "已連線", C_OK);
                SetReadout(_lblConnSha, "已驗證", C_OK);
                SetReadout(_lblConnProc, "PID " + (json.Get("pid") ?? "?"), C_TEXT);
                SetReadout(_lblConnTime, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"), C_TEXT_DIM);
                SetReadout(_lblBaseline, ready ? "READY" : "NOT READY", ready ? C_OK : C_BAD);
                _baselineReady = ready;
                SetBusy(false, null);

                // Single ActivePlayerContext: updated only after a verified read.
                string addr = json.Get("player_address");
                SetActiveContext(readSource, addr, name, face,
                    mem != null && mem.Count > 0 ? mem[0].Get("team_index") : null,
                    mem != null && mem.Count > 0 ? mem[0].Get("slot") : null,
                    mem != null && mem.Count > 0 ? mem[0].Get("team_name") : null);

                if (addr != null)
                    LogInfo(">>> 已取得球員資訊（address=" + addr + "，來源=" + (readSource == "RosterBrowser" ? "Roster 瀏覽" : "目前選中球員") + "）。");
                if (!ready)
                    LogWarning(">>> Baseline NOT READY：寫入按鈕已停用；先確認球員後再讀取以建立 baseline。");
            }
            catch (Exception ex)
            {
                SetReadout(_lblName, "已讀取", C_OK);
                SetReadout(_lblConnGame, "已連線", C_OK);
                _baselineReady = false;
                SetBusy(false, null);
                LogError("讀取報告解析失敗: " + ex.Message);
            }
        }

        private void MarkResult(string action)
        {
            switch (action)
            {
                case "attributes99":
                case "attributes110":
                case "max-badges":
                case "restore-abilities":
                case "restore-badges":
                    SetReadout(_lblConnTime, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"), C_TEXT_DIM);
                    LogInfo(">>> 完成：" + ActionLabel(action));
                    MessageBox.Show("操作完成：" + ActionLabel(action) + "。\n請查看日誌區與產物（dumps / analysis / logs）。",
                        "完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    break;
                case "dump":
                    LogInfo(">>> 完成：保存快照。");
                    break;
            }
        }

        private static string LastLine(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return "(無輸出)";
            var lines = s.Trim().Split('\n');
            return lines[lines.Length - 1].Trim();
        }

        private static string ParseField(string s, string key)
        {
            var m = Regex.Match(s, "\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
            return m.Success ? m.Groups[1].Value : null;
        }

        private static long ParseLong(string s, string key)
        {
            var m = Regex.Match(s, "\"" + key + "\"\\s*:\\s*(-?\\d+)");
            return m.Success ? long.Parse(m.Groups[1].Value) : -1;
        }

        private static string HumanSize(long bytes)
        {
            if (bytes < 0) return "?";
            string[] u = { "B", "KB", "MB", "GB" };
            double v = bytes; int i = 0;
            while (v >= 1024 && i < u.Length - 1) { v /= 1024; i++; }
            return v.ToString("0.#") + " " + u[i];
        }

        private static string ActionLabel(string action)
        {
            switch (action)
            {
                case "read": return "讀取目前球員";
                case "dump": return "保存快照";
                case "attributes99": return "全能力 99";
                case "attributes110": return "全能力 110";
                case "restore-abilities": return "恢復原能力";
                case "max-badges": return "全徽章";
                case "restore-badges": return "恢復原徽章";
                case "mc-enable": return "啟用離線 MyCAREER";
                case "mc-disable": return "停用離線 MyCAREER";
                case "ho-enable": return "解鎖隱藏選項";
                case "ho-disable": return "恢復隱藏選項";
                case "park-meta-apply": return "套用 2K21 PARK META";
                case "park-meta-curry": return "Curry 動作包";
                case "park-meta-lebron": return "LeBron 動作包";
                case "park-meta-kd": return "KD 動作包";
                case "park-meta-restore": return "恢復原動作";
                case "park-meta-migrate-name": return "設定 MC 姓名：Roxy Migurdia";
                default: return action;
            }
        }

        #endregion

        #region Logging

        private void Log(string text)
        {
            if (InvokeRequired) { BeginInvoke(new Action(() => Log(text))); return; }
            AppendLog(DateTime.Now.ToString("HH:mm:ss ") + text, C_TEXT);
        }

        private void LogInfo(string text)
        {
            if (InvokeRequired) { BeginInvoke(new Action(() => LogInfo(text))); return; }
            AppendLog(DateTime.Now.ToString("HH:mm:ss ") + text, C_OK);
        }

        private void LogWarning(string text)
        {
            if (InvokeRequired) { BeginInvoke(new Action(() => LogWarning(text))); return; }
            AppendLog(DateTime.Now.ToString("HH:mm:ss ") + text, C_WARN);
        }

        private void LogError(string text)
        {
            if (InvokeRequired) { BeginInvoke(new Action(() => LogError(text))); return; }
            AppendLog(DateTime.Now.ToString("HH:mm:ss ") + text, C_BAD);
        }

        private void AppendLog(string line, Color color)
        {
            _log.SelectionStart = _log.TextLength;
            _log.SelectionLength = 0;
            _log.SelectionColor = color;
            _log.AppendText(line + "\r\n");
            _log.ScrollToCaret();
            _log.SelectionColor = C_TEXT;
        }

        #endregion

        private sealed class BackendResult
        {
            public string Action;
            public int ExitCode;
            public string Stdout;
            public string Stderr;
            public BackendResult(string action, int exit, string o, string e)
            { Action = action; ExitCode = exit; Stdout = o; Stderr = e; }
        }
    }
}