// End-to-end test of the whole app: the 13 manual checks of the spec's
// testing section, run in a real browser against the running frontend and
// backend, with the real Supabase project and Gemini.
//
// It creates a throwaway user (e2e-xxxx@example.com) and deletes it with all
// its data afterwards, even if a check fails.
//
// Prerequisites: backend on NEXT_PUBLIC_API_URL with this origin in
// CORS_ORIGINS, frontend running (npm run dev / npm start), backend/venv set up.
//
//   npm run test:e2e
//
// Environment (all optional):
//   E2E_BASE_URL  frontend URL           (default http://localhost:3000)
//   E2E_BROWSER   installed browser      (default msedge on Windows, chrome elsewhere)
//   E2E_PYTHON    backend Python         (default backend/venv)
//   E2E_HEADED=1  show the browser window
import { execFileSync } from "node:child_process"
import { existsSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

import { chromium } from "playwright-core"

const here = dirname(fileURLToPath(import.meta.url))
const backendDir = join(here, "..", "..", "backend")
const windows = process.platform === "win32"
const BASE = (process.env.E2E_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "")
const python =
  process.env.E2E_PYTHON ?? join(backendDir, "venv", windows ? "Scripts/python.exe" : "bin/python")
const failureShot = join(here, "failure.png")

/** Run a backend helper command; returns its JSON output (the last line). */
function helper(...args) {
  const output = execFileSync(python, ["-m", "scripts.e2e_helper", ...args], {
    cwd: backendDir,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  })
  return JSON.parse(output.toString().trim().split("\n").pop())
}

let failures = 0
function check(label, ok, detail = "") {
  if (!ok) failures++
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail !== "" ? `  ->  ${detail}` : ""}`)
}

if (!existsSync(python)) {
  console.error(`Python not found at ${python}. Set up backend/venv or set E2E_PYTHON.`)
  process.exit(1)
}
try {
  await fetch(BASE)
} catch {
  console.error(`The frontend is not reachable at ${BASE}. Start it or set E2E_BASE_URL.`)
  process.exit(1)
}

const workDir = mkdtempSync(join(tmpdir(), "kb-e2e-"))
const pdfPath = join(workDir, "Georgia_Field_Guide.pdf")
helper("pdf", pdfPath)
const user = helper("signup")
console.log(`Test user ${user.email} -> ${BASE}\n`)

const browser = await chromium.launch({
  channel: process.env.E2E_BROWSER ?? (windows ? "msedge" : "chrome"),
  headless: process.env.E2E_HEADED !== "1",
})
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
const pageErrors = []
page.on("pageerror", (error) => pageErrors.push(error.message))
page.on("response", (response) => response.status() >= 500 && pageErrors.push(`${response.status()} ${response.url()}`))

/** Send a question in the open chat; returns the answer text and its source pages. */
async function ask(question) {
  const composer = page.getByLabel("Ask a question about this document")
  const before = await page.locator("ol > li").count()
  await composer.fill(question)
  await composer.press("Enter")
  const answer = page.locator("ol > li").nth(before + 1)
  await answer.getByText("Sources", { exact: true }).or(answer.getByRole("alert")).waitFor({ timeout: 120_000 })
  const text = await answer.innerText()
  const pages = (await answer.locator("span[title^='Page ']").allInnerTexts()).map((t) => Number(t.replace(/\D/g, "")))
  return { text, pages }
}

async function signOut() {
  await page.getByRole("button", { name: user.email }).click()
  await page.getByRole("menuitem", { name: "Sign out" }).click()
  await page.waitForURL("**/login")
}

try {
  console.log("1. Register")
  await page.goto(`${BASE}/register`)
  await page.getByLabel("Email").fill(user.email)
  await page.getByLabel("Password", { exact: true }).fill("short")
  await page.getByRole("button", { name: "Create account" }).click()
  check("weak password rejected in the form", (await page.locator("form [role=alert]").innerText()).includes("at least 8"))
  check("account starts unconfirmed (email confirmation on)", user.confirmed === false)
  await page.goto(`${BASE}/auth/callback?token_hash=${encodeURIComponent(user.token_hash)}&type=signup&next=/dashboard`)
  await page.waitForURL("**/dashboard")
  await page.getByText("No documents yet").waitFor()
  check("confirmation link signs the new user in -> /dashboard", true)

  console.log("2. Login")
  await signOut()
  await page.goto(`${BASE}/dashboard`)
  check("signed out: /dashboard -> /login", page.url().includes("/login?next="))
  await page.getByLabel("Email").fill(user.email)
  await page.getByLabel("Password", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL("**/dashboard")
  check("login with email + password", true)

  console.log("3-7. Upload, document appears, PDF stored, chunks, embeddings")
  await page.locator('input[type="file"]').setInputFiles(pdfPath)
  await page.getByRole("heading", { name: "Georgia Field Guide" }).waitFor({ timeout: 240_000 })
  check("document appears on the dashboard", await page.getByText("12 pages").first().isVisible())
  let state = helper("check", user.id)
  check("PDF stored in Supabase Storage", state.stored_files === 1, state.stored_files)
  check("chunks created", state.chunks >= 12, state.chunks)
  check("every chunk has an embedding", state.embedded === state.chunks, `${state.embedded}/${state.chunks}`)

  console.log("8. Chat works")
  await page.getByRole("button", { name: "Chat", exact: true }).first().click()
  await page.waitForURL("**/chat/new?document=*")
  await page.getByText("Ask about").waitFor()
  await page.goBack()
  await page.waitForURL("**/dashboard")
  check("opening and leaving a chat creates no conversation", helper("check", user.id).conversations === 0)
  await page.getByRole("button", { name: "Chat", exact: true }).first().click()
  await page.getByText("Ask about").waitFor()

  console.log("9. Sources show the correct pages")
  const expected = [
    ["How high is the Enguri Dam?", "271", 4],
    ["When was the Rikoti tunnel completed, and how long is it?", "1984", 11],
    ["Which architect rebuilt the cathedral in Mtskheta?", "Arsukisdze", 6],
  ]
  for (const [index, [question, fact, pageNumber]] of expected.entries()) {
    const { text, pages } = await ask(question)
    check(`"${question}" -> ${fact}, source page ${pageNumber}`, text.includes(fact) && pages.includes(pageNumber), `pages ${pages.join(",")}`)
    if (index === 0) {
      check("first question created the conversation; URL is /chat/<id>", /\/chat\/[0-9a-f-]{36}$/.test(page.url()), page.url().replace(BASE, ""))
    }
  }
  const followUp = await ask("How many plant species does the botanical garden there have?")
  check("question about another page -> page 9", followUp.pages.includes(9) && followUp.text.includes("5,000"), `pages ${followUp.pages.join(",")}`)
  check("sidebar lists the conversation by its first question", await page.getByRole("link", { name: "How high is the Enguri Dam?" }).isVisible())

  console.log("10. Conversation persists")
  await page.reload()
  await page.locator("ol > li").nth(7).waitFor({ timeout: 30_000 })
  check(
    "after reload: 8 messages with sources",
    (await page.locator("ol > li").count()) === 8 && (await page.locator("span[title^='Page ']").count()) >= 4,
  )

  console.log("11-12. Summary and questions")
  await page.getByRole("link", { name: "Georgia Field Guide" }).first().click()
  await page.waitForURL("**/documents/*")
  await page.getByRole("button", { name: "Generate summary" }).first().click()
  await page.getByText("Key points").waitFor({ timeout: 180_000 })
  const summary = (await page.locator("section[aria-label='Summary']").innerText()).toLowerCase()
  const covered = ["kazreti", "enguri", "vardzia", "batumi", "rikoti", "alphabet"].filter((k) => summary.includes(k))
  check("summary covers the whole document (first to last page)", covered.length >= 5, covered.join(", "))
  await page.getByRole("button", { name: "Generate questions" }).first().click()
  const questions = page.locator("section[aria-label='Suggested questions'] li button")
  await questions.first().waitFor({ timeout: 120_000 })
  check("suggested questions generated", (await questions.count()) === 6, await questions.count())
  check("document page lists the conversation", await page.locator("main aside").getByRole("link", { name: /How high is the Enguri Dam/ }).isVisible())

  console.log("13. Logout")
  await signOut()
  await page.goto(`${BASE}/documents`)
  check("logged out: app pages redirect to /login", page.url().includes("/login?next="))

  state = helper("check", user.id)
  check(
    "final DB state",
    state.documents === 1 && state.conversations === 1 && state.messages === 8 && state.with_summary === 1 && state.with_questions === 1,
    JSON.stringify(state),
  )
} catch (error) {
  failures++
  console.log("  [FAIL] scenario stopped:", error.message.split("\n")[0])
  await page.screenshot({ path: failureShot }).catch(() => {})
  console.log(`  screenshot: ${failureShot}`)
} finally {
  check("no page errors or 5xx responses", pageErrors.length === 0, pageErrors.join(" | "))
  await browser.close()
  helper("delete", user.id)
  rmSync(workDir, { recursive: true, force: true })
  console.log(`\nTest user deleted. ${failures ? `${failures} check(s) FAILED.` : "All checks passed."}`)
  process.exitCode = failures ? 1 : 0
}
