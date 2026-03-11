# Options Execution Playbook

## Mandatory Checklist

1. Audit live positions.
2. Audit live open orders.
3. Confirm target total quantity and budget.
4. Probe small first.
5. Wait about `50s`.
6. Recheck fills and resting orders.
7. Send only the remainder.
8. Cancel excess orders once target size is reached.

## Repo-Specific Notes

- Use `reqAllOpenOrders()` for visibility across clients.
- Cancellation may still require the owning client.
- Executor orders normally come from client `2`.
- Use paired `BAG` closes for spreads and calendars.
