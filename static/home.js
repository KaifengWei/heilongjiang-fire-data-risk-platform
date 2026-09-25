(() => {
  const canvas = document.getElementById('homeMapCanvas');
  const node = document.getElementById('homeRegionFeatures');
  if (!canvas || !node) return;
  let collection = {};
  try { collection = JSON.parse(node.textContent || '{}'); } catch (_) { return; }
  const features = Array.isArray(collection.features) ? collection.features : [];
  function ringsOf(g) { if (!g) return []; if (g.type === 'Polygon') return g.coordinates || []; if (g.type === 'MultiPolygon') return (g.coordinates || []).flat(); return []; }
  const all = [];
  features.forEach(f => ringsOf(f.geometry).forEach(r => r.forEach(p => all.push(p))));
  if (!all.length) return;
  const xs = all.map(p => Number(p[0])), ys = all.map(p => Number(p[1]));
  const bounds = {minX:Math.min(...xs),maxX:Math.max(...xs),minY:Math.min(...ys),maxY:Math.max(...ys)};
  function centroid(feature) { const pts=[]; ringsOf(feature.geometry).forEach(r=>r.forEach(p=>pts.push(p))); if(!pts.length)return null; return [pts.reduce((s,p)=>s+Number(p[0]),0)/pts.length,pts.reduce((s,p)=>s+Number(p[1]),0)/pts.length]; }
  const centers=features.map(centroid).filter(Boolean); let phase=0;
  function draw(){
    const rect=canvas.getBoundingClientRect(),dpr=Math.max(1,Math.min(2,window.devicePixelRatio||1)),width=Math.max(320,Math.round(rect.width||620)),height=Math.max(320,Math.round(rect.height||520));
    if(canvas.width!==width*dpr||canvas.height!==height*dpr){canvas.width=width*dpr;canvas.height=height*dpr;}
    const ctx=canvas.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,width,height);
    const pad=Math.max(28,width*.06),spanX=Math.max(.001,bounds.maxX-bounds.minX),spanY=Math.max(.001,bounds.maxY-bounds.minY),scale=Math.min((width-pad*2)/spanX,(height-pad*2)/spanY),ox=(width-spanX*scale)/2,oy=(height-spanY*scale)/2;
    const project=p=>[ox+(Number(p[0])-bounds.minX)*scale,height-(oy+(Number(p[1])-bounds.minY)*scale)];
    ctx.strokeStyle='rgba(122,224,245,.30)'; ctx.fillStyle='rgba(28,82,96,.18)'; ctx.lineWidth=1;
    features.forEach(f=>ringsOf(f.geometry).forEach(r=>{if(!r.length)return;ctx.beginPath();r.forEach((p,i)=>{const[x,y]=project(p);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.closePath();ctx.fill();ctx.stroke();}));
    phase+=.018; centers.forEach((p,i)=>{const[x,y]=project(p),pulse=(Math.sin(phase*4+i*.83)+1)/2,outer=5+pulse*8;ctx.beginPath();ctx.arc(x,y,outer,0,Math.PI*2);ctx.strokeStyle=`rgba(122,229,248,${.08+pulse*.18})`;ctx.stroke();ctx.beginPath();ctx.arc(x,y,1.5+pulse*1.2,0,Math.PI*2);ctx.fillStyle=`rgba(220,252,255,${.58+pulse*.4})`;ctx.fill();});
    requestAnimationFrame(draw);
  }
  draw();
})();
