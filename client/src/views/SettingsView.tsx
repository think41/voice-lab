export function SettingsView() {
  return (
    <div className="flex-1 bg-off p-6">
      <h1 className="text-lg font-semibold">Settings</h1>
      <div className="mt-4 max-w-2xl rounded-lg border border-line bg-white p-4 text-xs text-muted">
        Provider API keys are configured on the FastAPI server via `.env`. The UI stores agent runtime choices and sends them with the saved agent config.
      </div>
    </div>
  );
}
