"use client";

import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The shell every administrative page shares (PORTAL-001 / F-10).
 *
 * Six pages that all render "a title, an explanation, an error and a table"
 * is six chances to render an error differently. The explanation is not
 * decoration: these pages change who can do what, and an administrator who
 * cannot tell a deactivation from a deletion will eventually pick wrong.
 */
export function AdminPage({
  title,
  description,
  error,
  note,
  children,
}: {
  title: string;
  description: string;
  error?: string | null;
  note?: string | null;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 p-8">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          {note ? (
            <p role="status" className="text-sm text-muted-foreground">
              {note}
            </p>
          ) : null}
          {children}
        </CardContent>
      </Card>
    </main>
  );
}
