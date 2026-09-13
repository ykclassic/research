import type { PreferencesDraft, ResearchPreferences } from "../settingsApi";
import { SelectField, SettingField, SettingsSection, Toggle } from "./SettingsSection";
import { FlaskConical } from "lucide-react";

interface Props {
  settings: PreferencesDraft;
  update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void;
}

const ASSET_OPTIONS: Array<{ asset: string; assetClass: ResearchPreferences["default_asset_class"] }> = [
  { asset: "BTC/USD", assetClass: "Crypto" },
  { asset: "ETH/USD", assetClass: "Crypto" },
  { asset: "SOL/USD", assetClass: "Crypto" },
  { asset: "EUR/USD", assetClass: "Forex" },
  { asset: "GBP/USD", assetClass: "Forex" },
  { asset: "USD/JPY", assetClass: "Forex" },
  { asset: "AAPL", assetClass: "Stocks" },
  { asset: "MSFT", assetClass: "Stocks" },
  { asset: "NVDA", assetClass: "Stocks" },
  { asset: "SPY", assetClass: "Stocks" },
];

const TIMEFRAMES: ResearchPreferences["default_timeframe"][] = ["15m", "1h", "4h", "1D"];
const DEPTHS: ResearchPreferences["analysis_depth"][] = ["Quick", "Standard", "Comprehensive"];

export default function ResearchPreferencesSection({ settings, update }: Props) {
  const research = settings.research_preferences;

  const updateResearch = (patch: Partial<ResearchPreferences>) => {
    update("research_preferences", patch);
  };

  const handleAssetChange = (asset: string) => {
    const selected = ASSET_OPTIONS.find(option => option.asset === asset);
    updateResearch({
      default_asset: asset,
      ...(selected ? { default_asset_class: selected.assetClass } : {}),
    });
  };

  return (
    <SettingsSection
      title="Research Preferences"
      description="Set the defaults used by the research engine. These preferences select which evidence components are requested; they do not change the analytical algorithms."
      icon={FlaskConical}
    >
      <div className="settings-subheading">Default research settings</div>
      <div className="settings-control-grid">
        <SettingField
          label="Default asset"
          description="Used when a research request does not specify an asset."
        >
          <SelectField
            value={research.default_asset}
            onChange={handleAssetChange}
            options={ASSET_OPTIONS.map(option => option.asset)}
          />
        </SettingField>

        <SettingField
          label="Default asset class"
          description="Kept aligned with the selected default asset."
        >
          <SelectField
            value={research.default_asset_class}
            onChange={value => updateResearch({ default_asset_class: value as ResearchPreferences["default_asset_class"] })}
            options={["Crypto", "Forex", "Stocks"]}
          />
        </SettingField>

        <SettingField
          label="Default timeframe"
          description="Primary timeframe requested when an analysis component needs market candles."
        >
          <SelectField
            value={research.default_timeframe}
            onChange={value => updateResearch({ default_timeframe: value as ResearchPreferences["default_timeframe"] })}
            options={TIMEFRAMES}
          />
        </SettingField>

        <SettingField
          label="Default analysis depth"
          description="Controls the requested evidence window without changing indicator or model logic."
        >
          <SelectField
            value={research.analysis_depth}
            onChange={value => updateResearch({ analysis_depth: value as ResearchPreferences["analysis_depth"] })}
            options={DEPTHS}
          />
        </SettingField>
      </div>

      <div className="settings-subheading">Analysis preferences</div>
      <div className="settings-toggle-grid">
        <Toggle checked={research.technical_analysis_enabled} onChange={value => updateResearch({ technical_analysis_enabled: value })} label="Technical analysis" />
        <Toggle checked={research.market_structure_enabled} onChange={value => updateResearch({ market_structure_enabled: value })} label="Market structure" />
        <Toggle checked={research.multi_timeframe_enabled} onChange={value => updateResearch({ multi_timeframe_enabled: value })} label="Multi-timeframe analysis" />
        <Toggle checked={research.fundamental_analysis_enabled} onChange={value => updateResearch({ fundamental_analysis_enabled: value })} label="Fundamental analysis" />
        <Toggle checked={research.news_analysis_enabled} onChange={value => updateResearch({ news_analysis_enabled: value })} label="News analysis" />
        <Toggle checked={research.ai_interpretation_enabled} onChange={value => updateResearch({ ai_interpretation_enabled: value })} label="AI interpretation" />
      </div>

      <div className="settings-info-note">
        <strong>How this works</strong>
        <span>
          A research request first loads these saved preferences, then requests only the enabled analysis components. The underlying technical, structure, multi-timeframe, fundamental, news, and AI algorithms remain unchanged.
        </span>
      </div>
    </SettingsSection>
  );
}
