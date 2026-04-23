type ProgressBarProps = {
  value: number;
};

export default function ProgressBar({ value }: ProgressBarProps) {
  return (
    <div className="w-full bg-gray-800 rounded h-4 overflow-hidden">
      <div
        className="bg-green-600 h-4 transition-all"
        style={{ width: `${value}%` }}
      />
    </div>
  );
}