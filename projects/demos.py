"""Source-owned demonstrations; no invented client records or database seeds."""
DEMOS = {
    'stock-planner': {
        'title': 'StockPilot — Inventory Planning', 'category': 'Retail operations',
        'summary': 'Calculate reorder quantities from stock levels, daily demand, delivery lead time, and a safety buffer.',
        'problem': 'Small retailers need to decide what to reorder before stock runs out, without overbuying.',
        'solution': 'A transparent reorder calculation shows days of stock remaining, the reorder threshold, and a suggested purchase quantity.',
        'limit': 'Uses the numbers you enter. Supplier integrations, forecasting, and multi-location inventory are outside this demonstration.',
    },
    'appointment-desk': {
        'title': 'SlotDesk — Appointment Scheduler', 'category': 'Service businesses',
        'summary': 'Choose an appointment date and time, reserve a sample slot, and prevent duplicate bookings in this session.',
        'problem': 'Phone and message-based appointment handling can lead to double bookings and unclear availability.',
        'solution': 'A sample reservation list records selected slots and prevents a second reservation for the same date and time.',
        'limit': 'Bookings exist only in this page session. No real appointment, customer record, notification, or payment is created.',
    },
    'quote-builder': {
        'title': 'ScopeQuote — Service Quote Builder', 'category': 'Sales operations',
        'summary': 'Build a sample quotation with line items, quantities, discounts, and a clear total in PKR.',
        'problem': 'Manual quotations can contain inconsistent totals and make it difficult to explain the scope of a service.',
        'solution': 'Add service items and calculate subtotal, discount, and final total from the same visible line items.',
        'limit': 'Sample calculator only. Entered rates are not Codeventra Labs pricing; taxes, invoicing, and payment collection are not included.',
    },
    'support-triage': {
        'title': 'ResolveDesk — Support Triage', 'category': 'Customer support',
        'summary': 'Prioritize sample support requests using explicit impact and urgency rules.',
        'problem': 'Support teams need a consistent way to identify widespread outages and distinguish them from routine requests.',
        'solution': 'A visible priority matrix classifies each request and explains why it needs attention.',
        'limit': 'Rule-based demonstration, not AI. Priority suggestions do not send messages or create real support tickets.',
    },
}
