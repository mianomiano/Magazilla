const tg=window.Telegram?.WebApp;let userId=null;
document.addEventListener('DOMContentLoaded',function(){
const p=new URLSearchParams(window.location.search);
userId=p.get('user_id');
if(tg){tg.ready();tg.expand();if(tg.initDataUnsafe?.user)userId=tg.initDataUnsafe.user.id;}
if(userId){document.querySelectorAll('a[href*="/download/"]').forEach(l=>{if(!l.href.includes('user_id'))l.href+=(l.href.includes('?')?'&':'?')+'user_id='+userId;});}
if(p.get('filter')==='free')filterProducts('free');
document.querySelectorAll('.filter-btn').forEach(b=>b.addEventListener('click',function(){document.querySelectorAll('.filter-btn').forEach(x=>x.classList.remove('active'));this.classList.add('active');filterProducts(this.dataset.category);}));
});
function filterProducts(c){document.querySelectorAll('.product-card').forEach(d=>{if(c==='all')d.style.display='';else if(c==='free')d.style.display=d.dataset.free==='true'?'':'none';else d.style.display=d.dataset.category===c?'':'none';});}
function viewProduct(id){window.location.href='/product/'+id+(userId?'?user_id='+userId:'');}
function downloadProduct(id){
var url='/download/'+id+(userId?'?user_id='+userId:'');
if(tg){tg.openLink(window.location.origin+url);}
else{window.open(url,'_blank');}
}
async function buyProduct(pid,price){
if(!tg){showToast('Open in Telegram','error');return;}
showToast('Creating invoice...','success');
try{
const r=await fetch('/api/create-invoice-link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:pid})});
const d=await r.json();
if(d.invoice_link){
tg.openInvoice(d.invoice_link,function(s){
if(s==='paid'){showToast('Paid!','success');fetch('/api/verify-purchase',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:pid,user_id:userId,stars_paid:price})}).then(()=>setTimeout(()=>window.location.href='/product/'+pid+'?user_id='+userId,1000));}
else if(s==='cancelled')showToast('Cancelled','error');
else if(s==='failed')showToast('Failed','error');
});
}else showToast(d.error||'Error','error');
}catch(e){showToast('Error','error');}
}
function deleteProduct(id,n){if(confirm('Delete "'+n+'"?')){const f=document.createElement('form');f.method='POST';f.action='/admin/product/'+id+'/delete';document.body.appendChild(f);f.submit();}}
function previewImage(i,pid){const p=document.getElementById(pid);if(i.files&&i.files[0]){const f=i.files[0];if(f.type.startsWith('video/')){const v=document.createElement('video');v.autoplay=v.loop=v.muted=v.playsInline=true;v.style.cssText='max-width:120px;border-radius:8px;margin-top:10px';v.src=URL.createObjectURL(f);if(p){p.style.display='none';p.parentNode.insertBefore(v,p);}}else{const r=new FileReader();r.onload=e=>{p.src=e.target.result;p.style.display='block';};r.readAsDataURL(f);}}}
function updateFileName(i,lid){const l=document.getElementById(lid);if(i.files&&i.files[0])l.textContent=i.files[0].name;}
function togglePriceField(){const c=document.getElementById('is_free'),p=document.getElementById('price_field');if(c&&p)p.style.display=c.checked?'none':'block';}
function handleCategoryChange(s){const c=document.getElementById('custom_category_field');if(c)c.style.display=s.value==='_custom'?'block':'none';}
function showToast(m,t){const e=document.querySelector('.toast');if(e)e.remove();const d=document.createElement('div');d.className='toast '+(t||'success');d.textContent=m;document.body.appendChild(d);setTimeout(()=>d.remove(),3000);}
document.addEventListener('click',e=>{if(tg?.HapticFeedback&&e.target.matches('.neu-btn,.filter-btn,.product-card'))tg.HapticFeedback.impactOccurred('light');});
