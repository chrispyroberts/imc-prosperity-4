// shown only when --dro was used; contrasts nominal vs worst-case PnL per product.
import { Badge, Card, Table, Text } from '@mantine/core';
import type { DroReport } from '../../models';

export function DroOverlay({ report }: { report?: DroReport }) {
  if (!report) return null;
  const products = Object.keys(report.per_product_nominal_mean).sort();
  return (
    <Card withBorder mb="md">
      <Text fw={600} size="sm" mb="xs">
        DRO worst-case overlay (radius {report.radius.toFixed(2)}, k={report.k})
      </Text>
      <Text size="xs" c="dimmed" mb="md">
        Each session draws K adversarial parameter sets from a widened posterior;
        worst-case is the minimum PnL across K draws, averaged across sessions.
      </Text>
      <Table striped withTableBorder fz="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Scope</Table.Th>
            <Table.Th ta="right">Nominal mean PnL</Table.Th>
            <Table.Th ta="right">Worst-case mean</Table.Th>
            <Table.Th ta="right">Drop</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {products.map((p) => {
            const nom = report.per_product_nominal_mean[p];
            const worst = report.per_product_worst_mean[p];
            return (
              <Table.Tr key={p}>
                <Table.Td>{p}</Table.Td>
                <Table.Td ta="right">{nom.toFixed(0)}</Table.Td>
                <Table.Td ta="right">{worst.toFixed(0)}</Table.Td>
                <Table.Td ta="right">
                  <Badge color={worst < nom ? 'red' : 'green'} variant="light">
                    {(worst - nom).toFixed(0)}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            );
          })}
          <Table.Tr>
            <Table.Td fw={600}>Total</Table.Td>
            <Table.Td ta="right" fw={600}>{report.nominal_mean_pnl.toFixed(0)}</Table.Td>
            <Table.Td ta="right" fw={600}>{report.worst_case_mean_pnl.toFixed(0)}</Table.Td>
            <Table.Td ta="right" fw={600}>
              <Badge color="red" variant="light">
                {(report.worst_case_mean_pnl - report.nominal_mean_pnl).toFixed(0)}
              </Badge>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      <Text size="xs" c="dimmed" mt="xs">
        Worst-case P05 across sessions: {report.worst_case_p05_pnl.toFixed(0)}
      </Text>
    </Card>
  );
}
