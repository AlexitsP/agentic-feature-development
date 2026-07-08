/**
 * Index — redirect to the app (Gains Check).
 */
import { createFileRoute, redirect } from '@tanstack/react-router';

export const Route = createFileRoute('/')({
  beforeLoad: () => {
    throw redirect({ to: '/gains' });
  },
});
