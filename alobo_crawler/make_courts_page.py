#!/usr/bin/env python3
"""Sinh ../courts.html (trang công khai trên Vercel) từ viz/index.html.

viz/index.html là NGUỒN DUY NHẤT của giao diện heatmap. Trang công khai chỉ khác:
  - bỏ tab ⟳ Cào dữ liệu và ⚙ Cài đặt sân (người xem không được điều khiển crawler)
  - đọc dữ liệu từ /api/courts (do crawler đẩy lên) thay vì /api/data của server local
  - có link về Sổ cầu lông + dấu "cập nhật lúc"

Sửa giao diện ở viz/index.html, xong chạy:  python make_courts_page.py
Mỗi phép thay đều kiểm tra khớp đúng 1 lần — viz đổi cấu trúc thì script báo lỗi
ngay chứ không âm thầm sinh ra trang hỏng.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # console Windows không in nổi ✓
HERE = Path(__file__).resolve().parent
SRC = HERE / "viz" / "index.html"
OUT = HERE.parent / "courts.html"

s = SRC.read_text(encoding="utf-8")


def rep(old: str, new: str, count: int = 1) -> None:
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f"[make_courts_page] cần {count} chỗ khớp, thấy {n}: {old[:60]!r}")
    s = s.replace(old, new)


rep("<title>ALOBO · Sân trống</title>",
    '<title>Sân trống · Sổ Cầu Lông</title>\n<meta name="robots" content="noindex, nofollow" />')

# người xem không điều khiển crawler
rep('        <button data-v="crawl">⟳ Cào dữ liệu</button>\n', "")
rep('        <button data-v="settings">⚙ Cài đặt sân</button>\n', "")

# link về sổ + dấu thời gian
rep('    <h1 id="title">Sân trống</h1>',
    '    <a href="./" style="color:inherit;opacity:.7;text-decoration:none;font-size:13px;'
    'margin-right:8px">← Sổ cầu lông</a>\n'
    '    <h1 id="title">Sân trống</h1>\n'
    '    <span class="sub" id="pubStamp" style="margin-left:auto"></span>\n'
    '    <button id="crawlNow" hidden style="margin-left:8px;border:1px solid currentColor;background:none;'
    'color:inherit;border-radius:8px;padding:4px 10px;font:inherit;font-size:12px;cursor:pointer" '
    'title="Chỉ admin thấy nút này">⟳ Cào ngay</button>')

# viz ghi "cập nhật <giờ hiện tại của máy người xem>" — trên trang công khai câu đó nói dối
# (dữ liệu có thể cũ cả buổi). Giờ cào thật đã có ở #pubStamp, lấy từ server.
rep("${G.days.length} ngày · ${G.courts.length} sân · cập nhật ${(new Date()).toLocaleString('vi-VN')}",
    "${G.days.length} ngày · ${G.courts.length} sân")

# prefs cũ trỏ vào tab đã gỡ → về "Theo ngày"
rep("function render(){\n  savePrefs();",
    'function render(){\n  if(state.view==="crawl"||state.view==="settings") state.view="day";\n  savePrefs();')

rep("Chưa có dữ liệu. Vào tab ⚙ Cài đặt sân chọn sân, rồi bấm ⟳ Cào dữ liệu.",
    "Chưa có dữ liệu sân — máy cào chưa gửi lên lần nào.")

# nguồn dữ liệu: /api/courts (bọc {updatedAt, data})
LOADER = r"""
/* ---- trang công khai: dữ liệu do crawler đẩy lên /api/courts ---- */
function loadCourts(){
  return fetch('api/courts',{cache:'no-store'}).then(r=>{
    if(!r.ok) throw new Error('HTTP '+r.status);
    return r.json();
  }).then(j=>{
    window.LAST_AT=j.updatedAt||null;
    const el=document.getElementById('pubStamp');
    if(el){
      if(j.updatedAt){
        // Cào theo yêu cầu (không tự động) nên dữ liệu cũ là bình thường — chỉ nói rõ tuổi của nó.
        const t=new Date(j.updatedAt), mins=Math.max(0,Math.round((Date.now()-t)/60000));
        const age=mins<1?'vừa xong':mins<60?mins+' phút trước':mins<2880?Math.round(mins/60)+' giờ trước':Math.round(mins/1440)+' ngày trước';
        let admin=false; try{ admin=!!localStorage.getItem('caulong_pass'); }catch(e){}
        el.textContent='cào lúc '+t.toLocaleString('vi-VN',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})
          +' · '+age+(mins>180?(admin?' · bấm Cào ngay để lấy mới':' · sân có thể đã thay đổi'):'');
        el.style.color=mins>180?'#B7601F':'';
      } else el.textContent='chưa có dữ liệu';
    }
    return expandCourts(j.data||{branches:[],count:0,monitored:[]});
  });
}
/* push_web.py nén occupied thành chuỗi theo sân × ngày — giải nén về đúng shape viz cần */
function expandCourts(p){
  (p.branches||[]).forEach(g=>{
    if(!g.occ) return;
    const occ=[...(g.occ_extra||[])], codes=g.occ_codes||[];
    Object.entries(g.occ).forEach(([court,ds])=>Object.entries(ds).forEach(([date,row])=>{
      for(let i=0;i<row.length;i++){ const ch=row[i]; if(ch==='.') continue;
        occ.push({court,date,slot:g.slots[i],status:codes[ch.charCodeAt(0)-97]||'booked'}); }
    }));
    g.occupied=occ; delete g.occ; delete g.occ_extra;
  });
  return p;
}
/* Nút "Cào ngay": chỉ hiện khi máy này đã đăng nhập quản trị ở app sổ (chung domain nên
   đọc được mật khẩu đã lưu). Vercel kiểm lại mật khẩu rồi mới gọi server cào. */
(function(){
  let pass=''; try{ pass=localStorage.getItem('caulong_pass')||''; }catch(e){}
  const b=document.getElementById('crawlNow'); if(!pass||!b) return;
  b.hidden=false;
  b.onclick=async()=>{
    const el=document.getElementById('pubStamp'), before=window.LAST_AT;
    b.disabled=true; el.style.color=''; el.textContent='đang gửi lệnh cào…';
    try{
      const r=await fetch('api/courts?action=crawl',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({pass})});
      const j=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(j.error||('HTTP '+r.status));
      el.textContent='⟳ server đang cào… vài phút, trang tự cập nhật';
      for(let i=0;i<45;i++){                       // hỏi lại mỗi 20s, tối đa 15 phút
        await new Promise(r=>setTimeout(r,20000));
        const j2=await fetch('api/courts',{cache:'no-store'}).then(r=>r.json()).catch(()=>null);
        if(j2&&j2.updatedAt&&j2.updatedAt!==before) break;
      }
      reloadData();
    }catch(e){ el.style.color='#B23B3B'; el.textContent='✗ '+e.message; }
    b.disabled=false;
  };
})();
"""
rep("fetch('/api/data').then(r=>r.json()).then(boot)", LOADER.strip() + "\nloadCourts().then(boot)")
rep("  fetch('/api/data').then(r=>r.json()).then(p=>{", "  loadCourts().then(p=>{")

if "/api/config" in s.split("function renderSettings")[0]:
    raise SystemExit("[make_courts_page] còn gọi /api/config ngoài phần cài đặt — kiểm tra lại")

NOTE = ("<!-- FILE SINH TỰ ĐỘNG từ alobo_crawler/viz/index.html — đừng sửa tay, "
        "chạy alobo_crawler/make_courts_page.py -->")
head, nl, rest = s.partition("\n")          # giữ <!DOCTYPE> ở dòng đầu (tránh quirks mode)
if not head.lower().startswith("<!doctype"):
    raise SystemExit("[make_courts_page] viz/index.html phải mở đầu bằng <!DOCTYPE html>")
OUT.write_text(head + nl + NOTE + "\n" + rest, encoding="utf-8")
print(f"✓ đã sinh {OUT.relative_to(HERE.parent)} ({len(s)//1024}KB)")
