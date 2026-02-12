/// <reference types="cypress" />

describe("/activity feed", () => {
  const apiBase = "**/api/v1";
  const email = Cypress.env("CLERK_TEST_EMAIL") || "jane+clerk_test@example.com";

  function stubSseEmpty(pathGlob: string, alias: string) {
    cy.intercept("GET", pathGlob, {
      statusCode: 200,
      headers: {
        "content-type": "text/event-stream",
      },
      body: "",
    }).as(alias);
  }

  function assertSignedInAndLanded() {
    cy.waitForAppLoaded();
    cy.contains(/live feed/i).should("be.visible");
  }

  it("auth negative: signed-out user is redirected to sign-in", () => {
    // SignedOutPanel runs in redirect mode on this page.
    cy.visit("/activity");
    cy.location("pathname", { timeout: 20_000 }).should("match", /\/sign-in/);
  });

  it("happy path: renders feed items from the activity endpoint", () => {
    cy.intercept("GET", `${apiBase}/boards*`, {
      statusCode: 200,
      body: {
        items: [{ id: "b1", name: "Testing", updated_at: "2026-02-07T00:00:00Z" }],
      },
    }).as("boardsList");

    cy.intercept("GET", `${apiBase}/boards/b1/snapshot*`, {
      statusCode: 200,
      body: {
        tasks: [{ id: "t1", title: "CI hardening" }],
        agents: [],
        approvals: [],
        chat_messages: [],
      },
    }).as("boardSnapshot");

    cy.intercept("GET", `${apiBase}/activity*`, {
      statusCode: 200,
      body: {
        items: [
          {
            id: "evt-1",
            created_at: "2026-02-07T00:00:00Z",
            event_type: "task.comment",
            message: "Hello world",
            agent_id: null,
            task_id: "t1",
          },
        ],
      },
    }).as("activityList");

    // Prevent SSE connections from hanging the test.
    stubSseEmpty(`${apiBase}/boards/b1/tasks/stream*`, "tasksStream");
    stubSseEmpty(`${apiBase}/boards/b1/approvals/stream*`, "approvalsStream");
    stubSseEmpty(`${apiBase}/boards/b1/memory/stream*`, "memoryStream");
    stubSseEmpty(`${apiBase}/agents/stream*`, "agentsStream");

    cy.visit("/sign-in");
    cy.clerkLoaded();
    cy.clerkSignIn({ strategy: "email_code", identifier: email });

    cy.visit("/activity");
    assertSignedInAndLanded();

    cy.contains("CI hardening").should("be.visible");
    cy.contains("Hello world").should("be.visible");
  });

  it("empty state: shows waiting message when no items", () => {
    cy.intercept("GET", `${apiBase}/boards*`, {
      statusCode: 200,
      body: { items: [] },
    }).as("boardsList");

    cy.intercept("GET", `${apiBase}/activity*`, {
      statusCode: 200,
      body: { items: [] },
    }).as("activityList");

    stubSseEmpty(`${apiBase}/agents/stream*`, "agentsStream");

    cy.visit("/sign-in");
    cy.clerkLoaded();
    cy.clerkSignIn({ strategy: "email_code", identifier: email });

    cy.visit("/activity");
    assertSignedInAndLanded();

    cy.contains(/waiting for new activity/i).should("be.visible");
  });

  it("error state: shows failure UI when API errors", () => {
    cy.intercept("GET", `${apiBase}/boards*`, {
      statusCode: 200,
      body: { items: [] },
    }).as("boardsList");

    cy.intercept("GET", `${apiBase}/activity*`, {
      statusCode: 500,
      body: { detail: "boom" },
    }).as("activityList");

    stubSseEmpty(`${apiBase}/agents/stream*`, "agentsStream");

    cy.visit("/sign-in");
    cy.clerkLoaded();
    cy.clerkSignIn({ strategy: "email_code", identifier: email });

    cy.visit("/activity");
    assertSignedInAndLanded();

    cy.contains(/unable to load activity feed|boom/i).should("be.visible");
  });
});
