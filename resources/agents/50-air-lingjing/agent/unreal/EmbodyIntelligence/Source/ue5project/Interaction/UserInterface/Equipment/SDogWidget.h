#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class SCameraView;
class SCommandHistoryPanel;
class SEquipmentInfoPanel;
class SEquipmentMiniMap;

class SDogWidget : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SDogWidget) {}
	SLATE_ARGUMENT(UTextureRenderTarget2D*, FrontRenderTarget)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

protected:
	void OnEquipmentTransformUpdated(const FTransform& InTransform) const;
	void OnEquipmentMoved(const FVector2D& InPoint) const;
	void OnCommandAdd(const FString& InType, const FString& InContent) const;

	TSharedPtr<SEquipmentMiniMap> MiniMap;
	TSharedPtr<SEquipmentInfoPanel> InfoPanel;
	TSharedPtr<SCommandHistoryPanel> CommandHistory;
	TSharedPtr<SCameraView> FrontCameraView;
};
