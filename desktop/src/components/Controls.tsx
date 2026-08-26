import { open } from "@tauri-apps/plugin-dialog";
import { FolderOpen, Play, Upload } from "lucide-react";
import type { ReactNode } from "react";

interface FieldProps {
  label: string;
  children: ReactNode;
  hint?: string;
}

export function Field({ label, children, hint }: FieldProps) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

interface PathFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  directory?: boolean;
  placeholder?: string;
  filters?: { name: string; extensions: string[] }[];
}

export function PathField({
  label,
  value,
  onChange,
  directory = false,
  placeholder,
  filters,
}: PathFieldProps) {
  async function choosePath() {
    const selected = await open({ directory, multiple: false, filters });
    if (typeof selected === "string") onChange(selected);
  }

  return (
    <Field label={label}>
      <span className="path-control">
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
        <button
          className="icon-button"
          type="button"
          onClick={() => void choosePath()}
          title={directory ? "选择目录" : "选择文件"}
        >
          {directory ? <FolderOpen size={17} /> : <Upload size={17} />}
        </button>
      </span>
    </Field>
  );
}

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function Toggle({ label, checked, onChange }: ToggleProps) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true">
        <span />
      </span>
    </label>
  );
}

interface SubmitButtonProps {
  label?: string;
  busy?: boolean;
}

export function SubmitButton({ label = "开始处理", busy = false }: SubmitButtonProps) {
  return (
    <button className="primary-button" type="submit" disabled={busy}>
      <Play size={17} fill="currentColor" />
      {busy ? "正在提交" : label}
    </button>
  );
}
