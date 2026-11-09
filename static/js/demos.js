(() => {
  'use strict';
  const workspace = document.querySelector('[data-demo]');
  if (!workspace) return;
  const form = document.getElementById('demo-form');
  const result = document.getElementById('demo-result');
  const records = document.getElementById('demo-records');
  let bookings = new Set();
  let subtotal = 0;
  const money = value => new Intl.NumberFormat('en-PK', {style:'currency',currency:'PKR'}).format(value);
  const addRecord = text => {const item = document.createElement('li'); item.textContent = text; records.appendChild(item);};
  const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Karachi',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const setDate = () => {if(form.elements.date){form.elements.date.min=today();form.elements.date.value=today();}};
  setDate();
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const number = name => Number(data.get(name));
    switch (workspace.dataset.demo) {
      case 'stock-planner': {
        const stock=number('stock'), demand=number('demand'), lead=number('lead'), buffer=number('buffer'), coverage=number('coverage');
        const threshold=demand*lead+buffer;
        const target=demand*Math.max(coverage,lead)+buffer;
        result.textContent=`Stock coverage: ${(stock/demand).toFixed(1)} days.\nReorder threshold: ${threshold} units (${demand} × ${lead} + ${buffer}).\n${stock<=threshold?'Reorder now':'Above reorder threshold'}. Suggested order to reach target: ${Math.max(0,target-stock)} units.\nTarget uses the greater of lead time and target coverage, plus safety stock.`;
        break;
      }
      case 'appointment-desk': {
        if (data.get('date')<today()) {result.textContent='Choose today or a future date.';return;}
        const key=`${data.get('date')} at ${data.get('time')} PKT`;
        if(bookings.has(key)){result.textContent='This sample slot is already reserved. Choose another date or time.';return;}
        bookings.add(key);addRecord(key);result.textContent=`Sample reservation confirmed: ${key}. No real appointment has been booked.`;break;
      }
      case 'quote-builder': {
        const name=String(data.get('item')).trim();
        if(!name){result.textContent='Enter a service description.';return;}
        const amount=Math.round(number('quantity')*number('rate')*100)/100;
        subtotal=Math.round((subtotal+amount)*100)/100;
        const deduction=Math.round(subtotal*number('discount'))/100;
        addRecord(`${name} — ${number('quantity')} × ${money(number('rate'))} = ${money(amount)}`);
        result.textContent=`Subtotal: ${money(subtotal)}\nDiscount (${number('discount')}% on all items): ${money(deduction)}\nTotal: ${money(subtotal-deduction)}. Taxes excluded. Sample rates only.`;break;
      }
      case 'support-triage': {
        const subject=String(data.get('subject')).trim();
        if(!subject){result.textContent='Enter a sample request.';return;}
        const score=number('impact')*number('urgency');
        const priority=score>=9?'P1 — Critical':score>=6?'P2 — High':score>=3?'P3 — Normal':'P4 — Low';
        addRecord(`${subject}: ${priority}`);
        result.textContent=`${priority}\nImpact × urgency = ${score}. Priority rules: 9 = critical; 6–8 = high; 3–5 = normal; 1–2 = low.\nThis suggestion uses only your selected impact and urgency.`;break;
      }
    }
  });
  document.getElementById('demo-reset').addEventListener('click',()=>{
    form.reset();bookings=new Set();subtotal=0;records.replaceChildren();setDate();result.textContent='Demonstration reset. Your results will appear here.';
  });
})();
