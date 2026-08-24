import React from "react";
import { Link } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <AppLayout size="content">
      <div className="flex flex-col items-start gap-4 py-24">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-faint">404</p>
        <h1 className="font-heading text-4xl font-bold tracking-tight text-ink">
          This page doesn&apos;t exist.
        </h1>
        <p className="max-w-md text-base text-ink-muted">
          The link may be old, or the analysis it pointed to was never created.
        </p>
        <div className="mt-2 flex gap-3">
          <Button onClick={() => (window.location.href = "/")}>Go home</Button>
          <Button variant="secondary" as={Link} to="/analyze">
            New analysis
          </Button>
        </div>
      </div>
    </AppLayout>
  );
}
