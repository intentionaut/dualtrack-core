(function(){
  var root=document.documentElement, btn=document.getElementById('theme');
  var sys=window.matchMedia('(prefers-color-scheme: dark)');
  function saved(){try{return localStorage.getItem('dualtrack-theme')}catch(e){return null}}
  function apply(mode){
    root.classList.toggle('dark',mode==='dark'); root.classList.toggle('light',mode==='light');
    var dark=mode?mode==='dark':sys.matches, next=dark?'Light':'Dark';
    btn.textContent=next+' mode'; btn.setAttribute('aria-label','Switch to '+next.toLowerCase()+' mode');
  }
  apply(saved());
  sys.addEventListener('change',function(){if(!saved())apply(null)});
  btn.addEventListener('click',function(){
    var mode=root.classList.contains('dark')||(!root.classList.contains('light')&&sys.matches)?'light':'dark';
    try{localStorage.setItem('dualtrack-theme',mode)}catch(e){}
    apply(mode);
  });
})();

// Calls: each card builds the decide.py call. Served by dashboard_server.py (a dualtrack-live token in the page),
// the call is recorded at once and the page reloads from the record. Opened as a file, or with the server gone,
// it copies the exact command instead, so nothing is ever claimed that did not happen.
(function(){
  var q=function(t){return "'"+String(t).replace(/'/g,"'\\''")+"'"};
  var live=document.querySelector('meta[name=dualtrack-live]'), pass=live&&live.content;
  function call(f, alt){
    var k=f.dataset.kind, v=function(n){var i=f.querySelector('[name='+n+']');return i?i.value.trim():''};
    if(alt){ if(v('try')) return ['try',v('try')]; if(v('no')) return ['no',v('no')]; return null }
    if(k==='pick'){var o=f.querySelector('input[name=o]:checked');return o?[o.value,f.dataset.table]:null}
    if(k==='answer') return v('answer')?['answer',v('answer')]:null;
    if(k==='result'){var r=f.querySelector('input[name=v]:checked');return r?['result',f.dataset.title,r.value].concat(v('ev')?[v('ev')]:[]):null}
    if(k==='undo') return ['undo',f.dataset.title];
    if(k==='allow') return ['allow'];
    if(k==='resume') return ['resume'];
    if(k==='owner') return v('owner')?['owner',f.dataset.title,v('owner')]:null;
    return null;
  }
  function shell(f, argv){ return f.dataset.cmd+' '+argv.map(function(a,i){return i===0||/^\w+$/.test(a)?a:q(a)}).join(' ') }
  document.querySelectorAll('form.act').forEach(function(f){
    var html=f.innerHTML;
    function wire(){
      var b=f.querySelector('button[type=submit]');
      f.onchange=f.oninput=function(){ if(b&&f.dataset.kind!=='undo') b.disabled=!call(f) };
      var alt=f.querySelector('[data-alt]'); if(alt) alt.onclick=function(){ var a=call(f,true); if(a) send(a) };
    }
    function show(text, cmd){
      f.classList.add('done');
      f.innerHTML='<p></p>'+(cmd?'<code class="say"></code>':'')+'<button class="linkbtn" type="button">Change</button>';
      f.querySelector('p').textContent=text;
      if(cmd) f.querySelector('code').textContent=cmd;
      f.querySelector('.linkbtn').onclick=function(){ f.classList.remove('done'); f.innerHTML=html; wire() };
    }
    function copy(cmd, why){
      show((why||'Copied.')+' Paste into /dualtrack or your terminal:', cmd);
      var c=navigator.clipboard?navigator.clipboard.writeText(cmd):Promise.reject();
      c.catch(function(){ f.querySelector('p').textContent=(why?why+' ':'')+'Select and copy this, then paste into /dualtrack or your terminal:' });
    }
    function send(argv){
      var cmd=shell(f, argv);
      if(!pass) return copy(cmd);
      f.querySelectorAll('button').forEach(function(b){b.disabled=true});
      fetch('/call',{method:'POST',headers:{'Content-Type':'application/json','X-Dualtrack-Token':pass},body:JSON.stringify({argv:argv})})
        .then(function(r){return r.json()})
        .then(function(r){ if(r.code===0) location.reload(); else show(r.output||'Not recorded.', '') })
        .catch(function(){ copy(cmd, 'The local page has stopped, so nothing was recorded.') });
    }
    f.addEventListener('submit',function(e){ e.preventDefault(); var a=call(f); if(a) send(a) });
    wire();
  });
  document.querySelectorAll('tr.row').forEach(function(tr){
    function t(){var ev=tr.nextElementSibling,open=ev.hidden;ev.hidden=!open;tr.classList.toggle('open',open);tr.setAttribute('aria-expanded',open)}
    tr.addEventListener('click',t);tr.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();t()}});
  });
})();
