#include "SCarWidget.h"

#include "SubWidget/SCameraView.h"
#include "SubWidget/SCommandHistoryPanel.h"
#include "SubWidget/SEquipmentInfoPanel.h"
#include "SubWidget/SEquipmentMiniMap.h"
#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetController.h"

void SCarWidget::Construct(const FArguments& InArgs)
{
	const TWeakObjectPtr<UTextureRenderTarget2D> FrontRenderTarget = InArgs._FrontRenderTarget;

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		.Padding(20.f, 20.f, 0.f, 0.f)
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Top)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.Padding(0.f, 20.f, 0.f, 0.f)
			[
				SAssignNew(FrontCameraView, SCameraView)
				.RenderTarget(FrontRenderTarget)
			]
		]
		+ SOverlay::Slot()
		.Padding(0.f, 20.f, 20.f, 0.f)
		.HAlign(HAlign_Right)
		.VAlign(VAlign_Top)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SAssignNew(InfoPanel, SEquipmentInfoPanel)
			]
			+ SVerticalBox::Slot()
			.Padding(0.f, 20.f, 0.f, 0.f)
			[
				SAssignNew(CommandHistory, SCommandHistoryPanel)
			]
		]
	];

	FEquipmentWidgetController::Get()->OnEquipmentTransformUpdateDelegate.BindRaw(this, &SCarWidget::OnEquipmentTransformUpdated);
	FEquipmentWidgetController::Get()->OnTrajectoryPointAddedDelegate.BindRaw(this, &SCarWidget::OnEquipmentMoved);
	FEquipmentWidgetController::Get()->OnCommandAddedDelegate.BindRaw(this, &SCarWidget::OnCommandAdd);
}

void SCarWidget::OnEquipmentTransformUpdated(const FTransform& InTransform) const
{
	if (InfoPanel.IsValid())
	{
		InfoPanel->UpdateTransform(InTransform);
	}
}

void SCarWidget::OnEquipmentMoved(const FVector2D& InPoint) const
{
	if (MiniMap.IsValid())
	{
		MiniMap->AddTrajectoryPoint(InPoint);
	}
}

void SCarWidget::OnCommandAdd(const FString& InType, const FString& InContent) const
{
	if (CommandHistory.IsValid())
	{
		CommandHistory->AddCommand(InType, InContent);
	}
}
