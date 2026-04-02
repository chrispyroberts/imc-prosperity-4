import { Container, Group, Text } from '@mantine/core';
import { IconChartHistogram } from '@tabler/icons-react';
import { ReactNode } from 'react';
import { ColorSchemeSwitch } from './ColorSchemeSwitch.tsx';
import classes from './Header.module.css';

export function Header(): ReactNode {
  return (
    <header className={classes.header}>
      <Container size="md" className={classes.inner}>
        <Text size="xl" fw={700}>
          <IconChartHistogram size={30} className={classes.icon} />
          Prosperity 4 Monte Carlo
        </Text>

        <Group gap="sm">
          <ColorSchemeSwitch />
        </Group>
      </Container>
    </header>
  );
}
