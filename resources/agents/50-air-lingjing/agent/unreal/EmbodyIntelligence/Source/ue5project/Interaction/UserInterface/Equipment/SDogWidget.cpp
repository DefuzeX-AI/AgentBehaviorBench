#include "SDogWidget.h"

#include "SubWidget/SCameraView.h"
#include "SubWidget/SCommandHistoryPanel.h"
#include "SubWidget/SEquipmentInfoPanel.h"
#include "SubWidget/SEquipmentMiniMap.h"
#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetController.h"

void SDogWidget::Construct(const FArguments& InArgs)
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

	FEquipmentWidgetController::Get()->OnEquipmentTransformUpdateDelegate.BindRaw(this, &SDogWidget::OnEquipmentTransformUpdated);
	FEquipmentWidgetController::Get()->OnTrajectoryPointAddedDelegate.BindRaw(this, &SDogWidget::OnEquipmentMoved);
	FEquipmentWidgetController::Get()->OnCommandAddedDelegate.BindRaw(this, &SDogWidget::OnCommandAdd);
}

void SDogWidget::OnEquipmentTransformUpdated(const FTransform& InTransform) const
{
	if (InfoPanel.IsValid())
	{
		InfoPanel->UpdateTransform(InTransform);
	}
}

void SDogWidget::OnEquipmentMoved(const FVector2D& InPoint) const
{
	if (MiniMap.IsValid())
	{
		MiniMap->AddTrajectoryPoint(InPoint);
	}
}

void SDogWidget::OnCommandAdd(const FString& InType, const FString& InContent) const
{
	if (CommandHistory.IsValid())
	{
		CommandHistory->AddCommand(InType, InContent);
	}
}
