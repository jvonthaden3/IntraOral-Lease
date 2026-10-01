// Mirrors calc.py -- used for the live on-page preview. The server
// recomputes everything from scratch when a proposal is actually saved,
// so this copy only has to be good enough for instant feedback.
//
// Section 1 (equipment cost / lab financing) is fixed, admin-configured
// data injected by the server as window.LAB_SETTINGS -- there's nothing to
// read from the DOM for it. Section 2 (price to the doctor) only recomputes
// when the "Update" button is clicked, so the doctor's payment doesn't jump
// around while someone is still typing in that section. Sections 3, 4, and
// 5 (spend, credit %, per-unit profitability) recompute automatically on
// every change, since they only affect the schedule table below and should
// "just work" without an extra click.

function pmt(annualRate, termMonths, principal) {
  if (termMonths <= 0) return 0;
  const r = (annualRate || 0) / 12;
  if (r === 0) return principal / termMonths;
  return (principal * r * Math.pow(1 + r, termMonths)) / (Math.pow(1 + r, termMonths) - 1);
}

function roundToNearest(value, nearest) {
  if (!nearest) return value;
  return Math.round(value / nearest) * nearest;
}

function fmtUSD(n) {
  if (n === null || n === undefined || isNaN(n)) return '–';
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}
function fmtPct(n) {
  if (n === null || n === undefined || isNaN(n)) return '–';
  return (n * 100).toFixed(1) + '%';
}

function num(id) {
  const el = document.getElementById(id);
  const v = parseFloat(el.value);
  return isNaN(v) ? 0 : v;
}

function gatherInputs() {
  const s = window.LAB_SETTINGS;
  return {
    equipment_cost: s.equipment_cost,
    lab_down_payment: s.lab_down_payment,
    lab_apr: s.lab_apr,
    lab_term: s.lab_term,
    round_to: s.round_to,
    sell_price: num('sell_price'),
    discount: num('discount'),
    doctor_down_payment: num('doctor_down'),
    doctor_apr: num('doctor_apr') / 100,
    doctor_term: num('doctor_term'),
    credit_pct: num('credit_pct') / 100,
    low_threshold: num('low_threshold'),
    unit_cost: num('unit_cost'),
    unit_price: num('unit_price'),
    estimated_invoice: num('estimated_invoice'),
  };
}

function compute(inputs) {
  const labFinanced = Math.max(0, inputs.equipment_cost - inputs.lab_down_payment);
  const labPayment = pmt(inputs.lab_apr, inputs.lab_term, labFinanced);

  const discountedPrice = inputs.sell_price - inputs.discount;
  const doctorFinanced = Math.max(0, discountedPrice - inputs.doctor_down_payment);
  const doctorPaymentRaw = pmt(inputs.doctor_apr, inputs.doctor_term, doctorFinanced);
  const doctorPayment = inputs.round_to ? roundToNearest(doctorPaymentRaw, inputs.round_to) : doctorPaymentRaw;

  const marginPct = inputs.sell_price ? (inputs.sell_price - inputs.equipment_cost) / inputs.sell_price : 0;
  const monthlySpread = doctorPayment - labPayment;
  const tailMonths = Math.max(0, inputs.doctor_term - inputs.lab_term);
  const totalOverTerm = inputs.doctor_down_payment + doctorPayment * inputs.doctor_term;
  const totalMargin = monthlySpread * Math.min(inputs.lab_term, inputs.doctor_term)
    + doctorPayment * tailMonths
    + (inputs.doctor_down_payment - (inputs.equipment_cost - labFinanced));

  const breakeven = inputs.credit_pct ? doctorPayment / inputs.credit_pct : null;

  let profitPerUnit = null, profitMarginPct = null;
  if (inputs.unit_price) {
    profitPerUnit = inputs.unit_price - inputs.unit_cost;
    profitMarginPct = profitPerUnit / inputs.unit_price;
  }

  let levels;
  if (breakeven) {
    let top = Math.floor(breakeven / 500) * 500;
    if (top < breakeven) top += 500;
    top = Math.max(top, 500);
    levels = [];
    for (let v = top; v >= 500; v -= 500) levels.push(v);
  } else {
    levels = [3000, 2500, 2000, 1500, 1000, 500];
  }

  const schedule = levels.map(invoice => {
    const credit = invoice < inputs.low_threshold ? 0 : inputs.credit_pct * invoice;
    const creditApplied = Math.min(credit, doctorPayment);
    const doctorOwes = Math.max(0, doctorPayment - credit);
    const row = { invoice, credit_applied: creditApplied, doctor_owes: doctorOwes };
    if (profitPerUnit !== null && inputs.unit_price) {
      const units = invoice / inputs.unit_price;
      const profit = units * profitPerUnit;
      const netProfit = profit - creditApplied;
      row.profit = profit;
      row.net_profit = netProfit;
      row.net_margin_pct = invoice ? netProfit / invoice : 0;
    }
    return row;
  });

  return {
    lab: { equipment_cost: inputs.equipment_cost, financed: labFinanced, down_payment: inputs.lab_down_payment, monthly_payment: labPayment },
    doctor: { discounted_price: discountedPrice, down_payment: inputs.doctor_down_payment, financed: doctorFinanced, monthly_payment: doctorPayment, total_over_term: totalOverTerm },
    margin: { sell_margin_pct: marginPct, monthly_spread: monthlySpread, total_margin_over_term: totalMargin },
    credit_program: { breakeven_spend: breakeven },
    schedule
  };
}

function render() {
  const inputs = gatherInputs();
  const r = compute(inputs);

  const requiredPct = inputs.estimated_invoice ? r.doctor.monthly_payment / inputs.estimated_invoice : null;
  document.getElementById('required_pct_display').value = requiredPct !== null ? fmtPct(Math.min(requiredPct, 1)) + (requiredPct > 1 ? ' (can\'t fully cover at this spend)' : '') : '–';

  document.getElementById('r_doc_payment_inline').textContent = fmtUSD(r.doctor.monthly_payment) + ' /mo';

  document.getElementById('r_equipment_cost2').textContent = fmtUSD(r.lab.equipment_cost);
  document.getElementById('r_lab_down').textContent = fmtUSD(r.lab.down_payment);
  document.getElementById('r_lab_payment').textContent = fmtUSD(r.lab.monthly_payment) + ' /mo';
  document.getElementById('r_margin_pct').textContent = fmtPct(r.margin.sell_margin_pct);
  document.getElementById('r_spread').textContent = fmtUSD(r.margin.monthly_spread) + ' /mo';
  document.getElementById('r_total_margin').textContent = fmtUSD(r.margin.total_margin_over_term);

  document.getElementById('r_disc_price').textContent = fmtUSD(r.doctor.discounted_price);
  document.getElementById('r_doc_down').textContent = fmtUSD(r.doctor.down_payment);
  document.getElementById('r_doc_financed').textContent = fmtUSD(r.doctor.financed);
  document.getElementById('r_doc_payment').textContent = fmtUSD(r.doctor.monthly_payment) + ' /mo';
  document.getElementById('r_doc_total').textContent = fmtUSD(r.doctor.total_over_term);
  document.getElementById('r_breakeven').textContent = r.credit_program.breakeven_spend ? (fmtUSD(r.credit_program.breakeven_spend) + ' /mo') : '–';

  const tbody = document.querySelector('#schedule_table tbody');
  tbody.innerHTML = '';
  r.schedule.forEach(row => {
    const tr = document.createElement('tr');
    if (row.doctor_owes === 0) tr.className = 'highlight';
    tr.innerHTML = `<td>${fmtUSD(row.invoice)}</td><td>${fmtUSD(row.credit_applied)}</td><td>${fmtUSD(row.doctor_owes)}</td>` +
      `<td>${row.profit !== undefined ? fmtUSD(row.profit) : '–'}</td>` +
      `<td>${row.net_profit !== undefined ? fmtUSD(row.net_profit) : '–'}</td>` +
      `<td>${row.net_margin_pct !== undefined ? fmtPct(row.net_margin_pct) : '–'}</td>`;
    tbody.appendChild(tr);
  });
}

document.addEventListener('DOMContentLoaded', render);

// Every input on the page recomputes live, automatically, on every change --
// no button needed anywhere. This used to be gated behind an "Update" button
// for section 2 (sell price / discount / doctor down / APR / term), but that
// created a real risk: the on-screen preview could go stale if a field was
// edited again after clicking Update, while "Save & Generate Proposal" always
// saves whatever is currently typed -- so the saved proposal could end up
// with different numbers than what the screen last showed. Keeping
// everything live means what's on screen is always exactly what gets saved.
[
  'sell_price', 'discount', 'doctor_down', 'doctor_apr', 'doctor_term',
  'estimated_invoice', 'credit_pct', 'low_threshold', 'unit_cost', 'unit_price',
].forEach(id => {
  const el = document.getElementById(id);
  el.addEventListener('input', render);
  el.addEventListener('change', render);
});

// The Update button still works (just re-runs the same live calculation) --
// harmless to click, no longer required.
document.getElementById('btn_update').addEventListener('click', render);

document.getElementById('btn_use_required_pct').addEventListener('click', () => {
  const inputs = gatherInputs();
  const r = compute(inputs);
  if (!inputs.estimated_invoice) return;
  const requiredPct = r.doctor.monthly_payment / inputs.estimated_invoice;
  document.getElementById('credit_pct').value = (Math.min(requiredPct, 1) * 100).toFixed(1);
  render();
});

// Save & generate proposal
document.getElementById('btn_generate').addEventListener('click', async () => {
  const errEl = document.getElementById('err');
  errEl.style.display = 'none';

  const inputs = gatherInputs();
  const client = {
    practice_name: document.getElementById('cl_practice').value.trim(),
    doctor_name: document.getElementById('cl_doctor').value.trim(),
    email: document.getElementById('cl_email').value.trim(),
    phone: document.getElementById('cl_phone').value.trim(),
    address: document.getElementById('cl_address').value.trim(),
  };

  if (!client.practice_name) {
    errEl.textContent = 'Enter the client practice name before generating a proposal.';
    errEl.style.display = '';
    return;
  }

  try {
    const editTokenEl = document.getElementById('edit_token');
    const editToken = editTokenEl ? editTokenEl.value : '';

    if (editToken) {
      // Editing an existing proposal: update it in place, same link.
      const resp = await fetch('/api/proposals/' + editToken, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputs, client }),
      });
      if (!resp.ok) throw new Error((await resp.json()).error || 'Could not update proposal');
      const proposal = await resp.json();
      window.location.href = proposal.proposal_url;
      return;
    }

    let labToken = document.getElementById('lab_token').value;

    if (!labToken) {
      const labName = document.getElementById('lab_name').value.trim();
      if (!labName) {
        errEl.textContent = 'Enter your lab name before generating a proposal.';
        errEl.style.display = '';
        return;
      }
      const ownerNameEl = document.getElementById('owner_name');
      const labStateEl = document.getElementById('lab_state');
      const labResp = await fetch('/api/labs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: labName,
          contact_name: document.getElementById('lab_contact').value.trim(),
          email: document.getElementById('lab_email').value.trim(),
          phone: document.getElementById('lab_phone').value.trim(),
          address: document.getElementById('lab_address').value.trim(),
          owner_name: ownerNameEl ? ownerNameEl.value.trim() : '',
          state: labStateEl ? labStateEl.value.trim() : '',
        }),
      });
      if (!labResp.ok) throw new Error((await labResp.json()).error || 'Could not save lab profile');
      const lab = await labResp.json();
      labToken = lab.access_token;
    }

    const resp = await fetch('/api/proposals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lab_token: labToken, inputs, client }),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || 'Could not save proposal');
    const proposal = await resp.json();
    window.location.href = proposal.proposal_url;
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = '';
  }
});
