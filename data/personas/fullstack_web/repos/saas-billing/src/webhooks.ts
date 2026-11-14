export async function POST(req: Request) {
  const event = stripe.webhooks.constructEvent(await req.text(), sig, secret);
  if (event.type === "invoice.payment_failed") await startDunning(event.data.object);
}
