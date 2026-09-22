using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace V2FLSEngine.Gui
{
    /// <summary>Minimal tolerant JSON reader for backend report objects (C#5 / .NET Framework 4.0).</summary>
    internal sealed class SimpleJson
    {
        private readonly Dictionary<string, SimpleJson> _obj = new Dictionary<string, SimpleJson>();
        private readonly List<SimpleJson> _arr = new List<SimpleJson>();
        private readonly string _str;
        private readonly bool _isArray;

        private SimpleJson(string s) { _str = s; }
        private SimpleJson(List<SimpleJson> a) { _arr = a; _isArray = true; }
        private SimpleJson(Dictionary<string, SimpleJson> o) { _obj = o; }

        public static SimpleJson Parse(string text)
        {
            var p = new Parser(text);
            var v = p.ParseValue();
            p.SkipWs();
            if (p.Pos < text.Length) throw new InvalidOperationException("Trailing data in JSON.");
            return v;
        }

        public string Get(string key)
        {
            SimpleJson v;
            if (_obj != null && _obj.TryGetValue(key, out v))
            {
                if (v._str != null) return v._str;
                if (v._obj != null) return "{" + v._obj.Count + "}";
                return "[" + v._arr.Count + "]";
            }
            return null;
        }

        public List<SimpleJson> GetArray(string key)
        {
            SimpleJson v;
            if (_obj != null && _obj.TryGetValue(key, out v) && v._isArray)
                return v._arr;
            return null;
        }

        public SimpleJson GetChild(string key)
        {
            SimpleJson v;
            if (_obj != null && _obj.TryGetValue(key, out v))
                return v;
            return null;
        }

        public string GetStr(string key)
        {
            SimpleJson v;
            if (_obj != null && _obj.TryGetValue(key, out v) && v._str != null)
                return v._str;
            return null;
        }

        private sealed class Parser
        {
            public readonly string S;
            public int Pos;

            public Parser(string s) { S = s; }

            public void SkipWs()
            {
                while (Pos < S.Length && char.IsWhiteSpace(S[Pos])) Pos++;
            }

            public SimpleJson ParseValue()
            {
                SkipWs();
                if (Pos >= S.Length) throw new InvalidOperationException("Unexpected end.");
                char c = S[Pos];
                if (c == '{') return ParseObject();
                if (c == '[') return ParseArray();
                if (c == '"') return new SimpleJson(ParseString());
                if (c == 't') { Expect("true"); return new SimpleJson("true"); }
                if (c == 'f') { Expect("false"); return new SimpleJson("false"); }
                if (c == 'n') { Expect("null"); return new SimpleJson((string)null); }
                return new SimpleJson(ParseNumber());
            }

            private void Expect(string word)
            {
                if (Pos + word.Length > S.Length || S.Substring(Pos, word.Length) != word)
                    throw new InvalidOperationException("Unexpected token.");
                Pos += word.Length;
            }

            private SimpleJson ParseObject()
            {
                var d = new Dictionary<string, SimpleJson>();
                Pos++; // {
                SkipWs();
                if (Pos < S.Length && S[Pos] == '}') { Pos++; return new SimpleJson(d); }
                while (true)
                {
                    SkipWs();
                    if (Pos >= S.Length || S[Pos] != '"') throw new InvalidOperationException("Expected key.");
                    string key = ParseString();
                    SkipWs();
                    if (Pos >= S.Length || S[Pos] != ':') throw new InvalidOperationException("Expected ':'.");
                    Pos++;
                    d[key] = ParseValue();
                    SkipWs();
                    if (Pos >= S.Length) throw new InvalidOperationException("Unterminated object.");
                    if (S[Pos] == ',') { Pos++; continue; }
                    if (S[Pos] == '}') { Pos++; break; }
                    throw new InvalidOperationException("Expected ',' or '}'.");
                }
                return new SimpleJson(d);
            }

            private SimpleJson ParseArray()
            {
                var list = new List<SimpleJson>();
                Pos++; // [
                SkipWs();
                if (Pos < S.Length && S[Pos] == ']') { Pos++; return new SimpleJson(list); }
                while (true)
                {
                    list.Add(ParseValue());
                    SkipWs();
                    if (Pos >= S.Length) throw new InvalidOperationException("Unterminated array.");
                    if (S[Pos] == ',') { Pos++; continue; }
                    if (S[Pos] == ']') { Pos++; break; }
                    throw new InvalidOperationException("Expected ',' or ']'.");
                }
                return new SimpleJson(list);
            }

            private string ParseString()
            {
                Pos++; // "
                var sb = new StringBuilder();
                while (Pos < S.Length)
                {
                    char c = S[Pos++];
                    if (c == '"') return sb.ToString();
                    if (c == '\\')
                    {
                        if (Pos >= S.Length) break;
                        char e = S[Pos++];
                        switch (e)
                        {
                            case 'n': sb.Append('\n'); break;
                            case 'r': sb.Append('\r'); break;
                            case 't': sb.Append('\t'); break;
                            case 'b': sb.Append('\b'); break;
                            case 'f': sb.Append('\f'); break;
                            case 'u':
                                if (Pos + 4 <= S.Length)
                                {
                                    sb.Append((char)ushort.Parse(S.Substring(Pos, 4), NumberStyles.HexNumber));
                                    Pos += 4;
                                }
                                break;
                            default: sb.Append(e); break;
                        }
                    }
                    else sb.Append(c);
                }
                throw new InvalidOperationException("Unterminated string.");
            }

            private string ParseNumber()
            {
                int start = Pos;
                while (Pos < S.Length && (char.IsDigit(S[Pos]) || S[Pos] == '-' || S[Pos] == '+' || S[Pos] == '.' || S[Pos] == 'e' || S[Pos] == 'E'))
                    Pos++;
                return S.Substring(start, Pos - start);
            }
        }
    }
}