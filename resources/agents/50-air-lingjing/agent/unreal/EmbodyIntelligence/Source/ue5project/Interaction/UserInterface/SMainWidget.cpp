#include "SMainWidget.h"

void SMainWidget::Construct(const FArguments& InArgs)
{
	ChildSlot
	[
		SAssignNew(MainOverlay, SOverlay)
	];
}

TPanelChildren<SOverlay::FOverlaySlot>::FScopedWidgetSlotArguments SMainWidget::AddWidget() const
{
	return MainOverlay->AddSlot();
}

void SMainWidget::AddWidget(const TSharedRef<SWidget>& InWidget) const
{
	if (MainOverlay.IsValid())
	{
		MainOverlay->AddSlot()
		[
			InWidget
		];
	}
}

void SMainWidget::RemoveWidget(const TSharedRef<SWidget>& InWidget) const
{
	if (MainOverlay.IsValid())
	{
		MainOverlay->RemoveSlot(InWidget);
	}
}
