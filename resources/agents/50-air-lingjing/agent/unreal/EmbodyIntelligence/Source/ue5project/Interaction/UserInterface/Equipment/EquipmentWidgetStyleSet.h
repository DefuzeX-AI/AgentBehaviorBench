// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

class FEquipmentWidgetStyleSet final
{
	FEquipmentWidgetStyleSet()
	{
		{	// BackgroundImageBrush
			UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, TEXT("/Script/Engine.Texture2D'/EmbodyIntelligence/Program/UserInterface/Textures/EquipmentWidget/Background.Background'"));
			if (Texture)
			{
				Texture->AddToRoot();
			}
			FSlateImageBrush* ImageBrush = new FSlateImageBrush(Texture, FVector2D(414.0, 414.0));
			RegisterSlateBrush(TEXT("BackgroundImageBrush"), ImageBrush);
		}
		{	// MapImageBrush
			UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, TEXT("/Script/Engine.Texture2D'/EmbodyIntelligence/Program/UserInterface/Textures/EquipmentWidget/Map.Map'"));
			if (Texture)
			{
				Texture->AddToRoot();
			}
			FSlateImageBrush* ImageBrush = new FSlateImageBrush(Texture, FVector2D(512.0, 512.0));
			RegisterSlateBrush(TEXT("MapImageBrush"), ImageBrush);
		}
	}
	~FEquipmentWidgetStyleSet()
	{}

	TMap<FName, FSlateBrush*> BrushNameSlateBrushMap;
	void RegisterSlateBrush(const FName& BrushName, FSlateBrush* InBrush)
	{
		BrushNameSlateBrushMap.Add(BrushName, InBrush);
	}

public:
	static FEquipmentWidgetStyleSet* Get()
	{
		static FEquipmentWidgetStyleSet Instance;
		return &Instance;
	}

	FSlateBrush* GetBrush(const FName& BrushName) const
	{
		return BrushNameSlateBrushMap.FindRef(BrushName);
	}
};



