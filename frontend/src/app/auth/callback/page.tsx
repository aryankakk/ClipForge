'use client';

import { useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function CallbackContent() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const token = params.get('token');
    const login = params.get('login');

    if (!token) {
      router.replace('/');
      return;
    }

    localStorage.setItem('clipper_token', token);
    if (login) localStorage.setItem('clipper_login', login);

    router.replace('/dashboard');
  }, [params, router]);

  return <main>Connecting Twitch...</main>;
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<main>Connecting Twitch...</main>}>
      <CallbackContent />
    </Suspense>
  );
}