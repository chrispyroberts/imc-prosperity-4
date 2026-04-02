import { MantineColorScheme } from '@mantine/core';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Algorithm, MonteCarloDashboard } from './models.ts';

export interface State {
  colorScheme: MantineColorScheme;

  idToken: string;
  round: string;

  algorithm: Algorithm | null;
  monteCarlo: MonteCarloDashboard | null;

  setColorScheme: (colorScheme: MantineColorScheme) => void;
  setIdToken: (idToken: string) => void;
  setRound: (round: string) => void;
  setAlgorithm: (algorithm: Algorithm | null) => void;
  setMonteCarlo: (monteCarlo: MonteCarloDashboard | null) => void;
}

export const useStore = create<State>()(
  persist(
    set => ({
      colorScheme: 'auto',

      idToken: '',
      round: 'ROUND0',

      algorithm: null,
      monteCarlo: null,

      setColorScheme: colorScheme => set({ colorScheme }),
      setIdToken: idToken => set({ idToken }),
      setRound: round => set({ round }),
      setAlgorithm: algorithm => set({ algorithm, monteCarlo: null }),
      setMonteCarlo: monteCarlo => set({ monteCarlo, algorithm: null }),
    }),
    {
      name: 'prosperity4mcbt',
      partialize: state => ({
        colorScheme: state.colorScheme,
        idToken: state.idToken,
        round: state.round,
      }),
    },
  ),
);
