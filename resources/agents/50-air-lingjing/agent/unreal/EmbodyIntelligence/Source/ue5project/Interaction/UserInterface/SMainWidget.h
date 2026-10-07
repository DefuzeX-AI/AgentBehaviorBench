#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class SDogPanel;
class SCarWidget;
class SDroneWidget;

enum class EActivePanel : uint8
{
	None,
	Drone,
	Car,
	Dog
};

class SMainWidget : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SMainWidget) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	
	TPanelChildren<SOverlay::FOverlaySlot>::FScopedWidgetSlotArguments AddWidget() const;
	void AddWidget(const TSharedRef<SWidget>& InWidget) const;
	void RemoveWidget(const TSharedRef<SWidget>& InWidget) const;
protected:
	TSharedPtr<SOverlay> MainOverlay;
	
};
